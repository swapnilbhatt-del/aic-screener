"""Feedback loop measurement and fine-tuning readiness (lecture 24 Nov).

Disagreement score: the gap between what the system recommended and what Riya and the partners did, kept as
three separate signals (never blended into one number with made-up weights):
  * band      - model band vs the partner's recorded decision (partner_review is not a single recommendation,
                so it is counted separately, not as agreement or disagreement)
  * criteria  - share of scored criteria a human corrected, on companies a human has reviewed
  * email     - how much Riya changed the system's draft before approving it (0 = sent as drafted, 1 = rewritten)
Each is shown by month (it should fall, then plateau) and by sector (new sectors with no feedback spike).

Fine-tuning readiness: whether the lecture's conditions hold, against a PROPOSED bar in config `finetune.bar`
(Kushal sets it). It never trains anything; training is a separate, human-run step (Unsloth, self-managed).

Dataset export: input/output pairs built with the same prompts as the live app, deduplicated, capped per sector,
split 75/15/10 by a stable hash. Written to data/finetune/ (gitignored, founder data).

  python -m aic.learning disagreement
  python -m aic.learning readiness
  python -m aic.learning export
"""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from . import config, db, feedback

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "finetune"
BAND_TO_DECISION = {"call": "call", "pass": "pass", "hold": "hold"}


def _q(conn, sql, args=()):
    return [dict(zip([d[0] for d in cur.description], r)) for cur in [conn.execute(sql, args)] for r in cur.fetchall()]


def _rate(num: float, den: float) -> Optional[float]:
    return round(num / den, 3) if den else None


# ---- disagreement --------------------------------------------------------------------------
def band_signal(conn, cfg) -> dict:
    rows = _q(conn, "SELECT company, model_band, human_decision, decided_at FROM outcomes WHERE human_decision IS NOT NULL")
    sectors = {}
    by_month, by_sector = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    review = 0
    for r in rows:
        if r["model_band"] not in BAND_TO_DECISION:
            review += 1
            continue
        dis = int(BAND_TO_DECISION[r["model_band"]] != r["human_decision"])
        s = sectors.setdefault(r["company"], feedback.company_sector(r["company"], cfg))
        for bucket, key in ((by_month, (r["decided_at"] or "")[:7]), (by_sector, s)):
            bucket[key][0] += dis
            bucket[key][1] += 1
    n = sum(v[1] for v in by_month.values())
    return {"decided": len(rows), "compared": n, "partner_review_decided": review,
            "rate": _rate(sum(v[0] for v in by_month.values()), n),
            "by_month": [{"month": k, "rate": _rate(*v), "n": v[1]} for k, v in sorted(by_month.items())],
            "by_sector": [{"sector": k, "rate": _rate(*v), "n": v[1]} for k, v in sorted(by_sector.items())]}


def criteria_signal(conn, cfg) -> dict:
    bad = feedback.flagged_ids(conn, "correction")
    corr = [r for r in feedback._rows(conn) if r["id"] not in bad]
    decided = {r["company"] for r in _q(conn, "SELECT company FROM outcomes WHERE human_decision IS NOT NULL")}
    reviewed = decided | {r["company"] for r in corr}
    n_crit = len(cfg["criteria"])
    pairs = {(r["company"], r["criterion"]) for r in corr}
    by_month, by_sector = defaultdict(lambda: [set(), set()]), defaultdict(lambda: [set(), set()])
    for r in corr:
        for bucket, key in ((by_month, r["corrected_at"][:7]), (by_sector, r["sector"])):
            bucket[key][0].add((r["company"], r["criterion"]))
            bucket[key][1].add(r["company"])
    return {"reviewed_companies": len(reviewed), "corrections": len(corr), "flagged": len(bad),
            "this_case_only": sum(r.get("scope") == "this_case" for r in corr),
            "rate": _rate(len(pairs), len(reviewed) * n_crit),
            "mean_abs_change": round(sum(abs(r["human_score"] - r["model_score"]) for r in corr) / len(corr), 2) if corr else None,
            "by_month": [{"month": k, "rate": _rate(len(v[0]), len(v[1]) * n_crit), "n": len(v[1])} for k, v in sorted(by_month.items())],
            "by_sector": [{"sector": k, "rate": _rate(len(v[0]), len(v[1]) * n_crit), "n": len(v[1])} for k, v in sorted(by_sector.items())],
            "by_criterion": sorted(Counter(r["criterion"] for r in corr).items(), key=lambda x: -x[1])}


def email_signal(conn, cfg) -> dict:
    from difflib import SequenceMatcher
    sent = _q(conn, "SELECT id, company, subject, body, created_at FROM outbox WHERE status IN ('approved', 'sent')")
    edits = _q(conn, "SELECT * FROM email_edits ORDER BY id")
    first = {}
    for e in edits:
        first.setdefault(e["outbox_id"], e)
    by_month, by_sector, vals = defaultdict(list), defaultdict(list), []
    for r in sent:
        e = first.get(r["id"])
        ratio = 0.0 if not e else 1 - SequenceMatcher(None, e["before_subject"] + "\n" + e["before_body"],
                                                     r["subject"] + "\n" + r["body"]).ratio()
        vals.append(ratio)
        by_month[r["created_at"][:7]].append(ratio)
        by_sector[feedback.company_sector(r["company"], cfg)].append(ratio)
    avg = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    return {"approved_emails": len(sent), "edited": sum(v > 0 for v in vals), "edits_logged": len(edits),
            "flagged": len(feedback.flagged_ids(conn, "email_edit")), "rate": avg(vals),
            "by_month": [{"month": k, "rate": avg(v), "n": len(v)} for k, v in sorted(by_month.items())],
            "by_sector": [{"sector": k, "rate": avg(v), "n": len(v)} for k, v in sorted(by_sector.items())],
            "edit_reasons": [{"company": e["company"], "reason": e["reason"], "scope": e["scope"], "by": e["edited_by"],
                              "change": e["change_ratio"]} for e in edits[-20:]]}


def plateau(by_month: List[dict], cfg) -> Optional[dict]:
    """Last `plateau_months` monthly rates; plateaued if they moved less than `plateau_band`."""
    k, band = cfg["learning"]["plateau_months"], cfg["learning"]["plateau_band"]
    pts = [m["rate"] for m in by_month if m["rate"] is not None][-k:]
    if len(pts) < k:
        return None
    return {"months": k, "rates": pts, "plateaued": max(pts) - min(pts) < band, "level": round(sum(pts) / k, 3)}


def disagreement(conn=None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    conn = conn or db.connect()
    sig = {"band": band_signal(conn, cfg), "criteria": criteria_signal(conn, cfg), "email": email_signal(conn, cfg)}
    for s in sig.values():
        s["plateau"] = plateau(s["by_month"], cfg)
    # Spike risk: sectors in the current batch with no usable feedback of any kind (lecture: new categories spike).
    apps = sorted(p.stem for p in feedback.APPS.glob("*.json"))
    fed = {r["sector"] for r in feedback.usable_corrections(conn)} | \
          {r[0] for r in conn.execute("SELECT DISTINCT sector FROM email_edits WHERE scope='general'")}
    cur = Counter(feedback.company_sector(a, cfg) for a in apps)
    sig["cold_sectors"] = [{"sector": s, "applications": n} for s, n in sorted(cur.items()) if s not in fed]
    return sig


# ---- fine-tuning readiness ----------------------------------------------------------------------
def readiness(conn=None, cfg: Optional[dict] = None, dis: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    conn = conn or db.connect()
    dis = dis or disagreement(conn, cfg)
    bar = cfg["finetune"]["bar"]
    pairs = len(build_pairs(conn, cfg))
    groups = defaultdict(set)
    for r in feedback.usable_corrections(conn):
        groups[(r["criterion"], "up" if r["human_score"] > r["model_score"] else "down")].add(r["company"])
    worst = max(groups.items(), key=lambda kv: len(kv[1]), default=None)
    months = sorted({m["month"] for s in ("band", "criteria", "email") for m in dis[s]["by_month"]})
    stuck = [s for s in ("band", "criteria", "email")
             if dis[s]["plateau"] and dis[s]["plateau"]["plateaued"] and dis[s]["plateau"]["level"] > bar["disagreement_above"]
             and dis[s]["plateau"]["months"] >= bar["sustained_months"]]
    checks = [
        {"check": "Enough labelled pairs", "met": pairs >= bar["min_pairs"], "value": f"{pairs} of {bar['min_pairs']}"},
        {"check": f"Feedback for {bar['sustained_months']}+ months (post-launch)", "met": len(months) >= bar["sustained_months"],
         "value": f"{len(months)} month(s) with feedback"},
        {"check": f"Disagreement stuck above {int(bar['disagreement_above'] * 100)}%", "met": bool(stuck),
         "value": ", ".join(stuck) if stuck else "no signal has plateaued above the bar"},
        {"check": f"Same mistake {bar['repeat_mistake']}+ times", "met": bool(worst and len(worst[1]) >= bar["repeat_mistake"]),
         "value": (f"{worst[0][0]} {worst[0][1]} on {len(worst[1])} companies" if worst else "no repeated correction")},
    ]
    manual = ["Rubric descriptions improved for the failing criterion", "Scrapers and data sources improved",
              "A stronger model tried (Sonnet/Opus) on the same cases", "The rule being taught is stable (thesis not about to change)"]
    met = all(c["met"] for c in checks)
    return {"bar": bar, "bar_is_proposal": True, "checks": checks, "manual_checks": manual,
            "verdict": ("Consider fine-tuning, after a person confirms the manual checks" if met else
                        "Not yet: keep the feedback loop running and collect data"),
            "ready": met, "route": cfg["finetune"]["route"],
            "note": ("Fine-tuning would not replace the feedback loop: it keeps collecting data for the next retrain, "
                     "and catches part of what the tuned model misses. If the tuned model does not cross the bar on "
                     "the held-out test split, it is not deployed.")}


# ---- dataset ------------------------------------------------------------------------------------
def _latest_corrections(conn) -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for r in feedback.usable_corrections(conn):
        out[r["company"]][r["criterion"]] = r            # rows are in time order; the newest wins
    return out


def build_pairs(conn, cfg) -> List[dict]:
    """Input/output pairs in chat format, from the live prompts.

    scoring: input = the live scoring request (runner.build_request); output = the score card with each usable
             human correction applied (and its reason). Companies with no correction and no decision are skipped:
             an unreviewed model output is not a label.
    email:   input = the system's draft and its context; output = what Riya approved. Unedited approved emails
             count too (agreement is a label). 'this_case' and flagged edits are excluded.
    """
    from . import runner
    pairs = []
    corr = _latest_corrections(conn)
    decided = {r[0] for r in conn.execute("SELECT company FROM outcomes WHERE human_decision IS NOT NULL")}
    for co in sorted(set(corr) | decided):
        sc_path = ROOT / "data" / "scores" / f"{co}.json"
        if not sc_path.exists():
            continue
        try:
            req = runner.build_request("scoring", co, conn=None)       # the live prompt, without injected lessons
        except runner.RunError:
            continue
        sc = json.loads(sc_path.read_text())
        target = {}
        for k, c in sc["criteria"].items():
            fix = corr.get(co, {}).get(k)
            target[k] = {"score": fix["human_score"] if fix else c["final"],
                         "rationale": c["rationale"] + (f" [Corrected by {fix['corrected_by']}: {fix['reason']}]" if fix else "")}
        pairs.append({"task": "scoring", "company": co, "sector": feedback.company_sector(co, cfg),
                      "messages": [{"role": "system", "content": req["system"]}, req["messages"][0],
                                   {"role": "assistant", "content": json.dumps({"criteria": target}, ensure_ascii=False)}]})
    bad = feedback.flagged_ids(conn, "email_edit")
    edits = defaultdict(list)
    for e in _q(conn, "SELECT * FROM email_edits ORDER BY id"):
        edits[e["outbox_id"]].append(e)
    for r in _q(conn, "SELECT id, company, kind, subject, body FROM outbox WHERE status IN ('approved', 'sent')"):
        es = edits.get(r["id"], [])
        if any(e["id"] in bad or e["scope"] == "this_case" for e in es):
            continue
        draft = (es[0]["before_subject"], es[0]["before_body"]) if es else (r["subject"], r["body"])
        pairs.append({"task": "email", "company": r["company"], "sector": feedback.company_sector(r["company"], cfg),
                      "messages": [{"role": "system", "content": "Rewrite this All In Capital outreach draft the way Riya would send it."},
                                   {"role": "user", "content": json.dumps({"kind": r["kind"], "subject": draft[0], "body": draft[1]}, ensure_ascii=False)},
                                   {"role": "assistant", "content": json.dumps({"subject": r["subject"], "body": r["body"]}, ensure_ascii=False)}]})
    return pairs


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def export(conn=None, cfg: Optional[dict] = None, out: Path = OUT) -> dict:
    cfg = cfg or config.load()
    conn = conn or db.connect()
    pairs, seen, dups = [], set(), 0
    for p in build_pairs(conn, cfg):
        key = _h(json.dumps(p["messages"][:2], sort_keys=True))
        if key in seen:
            dups += 1
            continue
        seen.add(key)
        p["key"] = key
        pairs.append(p)
    cap = cfg["finetune"]["max_sector_share"]
    by_sector = defaultdict(list)
    for p in sorted(pairs, key=lambda p: p["key"]):
        by_sector[p["sector"]].append(p)
    kept, dropped = [], []
    limit = max(1, int(cap * len(pairs))) if len(by_sector) > 1 else len(pairs)
    for s, ps in by_sector.items():
        kept += ps[:limit]
        dropped += [{"company": p["company"], "task": p["task"], "sector": s} for p in ps[limit:]]
    split = cfg["finetune"]["split"]
    parts = {"train": [], "val": [], "test": []}
    for s in by_sector:                                   # stratified by sector, stable by hash
        ps = sorted((p for p in kept if p["sector"] == s), key=lambda p: p["key"])
        n = len(ps)
        a, b = round(n * split["train"]), round(n * (split["train"] + split["val"]))
        parts["train"] += ps[:a]
        parts["val"] += ps[a:b]
        parts["test"] += ps[b:]
    out.mkdir(parents=True, exist_ok=True)
    for name, ps in parts.items():
        (out / f"{name}.jsonl").write_text("".join(json.dumps({"messages": p["messages"]}, ensure_ascii=False) + "\n" for p in ps))
    manifest = {"pairs": len(kept), "duplicates_removed": dups, "dropped_for_sector_cap": dropped,
                "split": {k: len(v) for k, v in parts.items()}, "by_task": dict(Counter(p["task"] for p in kept)),
                "bar": cfg["finetune"]["bar"], "bar_is_proposal": True,
                "by_sector": dict(Counter(p["sector"] for p in kept)), "max_sector_share": cap,
                "format": "chat messages (system, user, assistant); same prompts as the live app",
                "note": "Founder data: keep in-house (self-managed route). Hold out test.jsonl until the final evaluation."}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def build(conn=None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    conn = conn or db.connect()
    dis = disagreement(conn, cfg)
    apps = sorted(p.stem for p in feedback.APPS.glob("*.json"))
    return {"disagreement": dis, "readiness": readiness(conn, cfg, dis),
            "lessons": {a: feedback.lessons(conn, a, cfg) for a in apps},
            "inject_rule": cfg["feedback"]["inject_min_agreeing_companies"],
            "flags": _q(conn, "SELECT target, target_id, kind, reason, flagged_by, flagged_at FROM feedback_flags ORDER BY id DESC LIMIT 20")}


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["disagreement"]:
        print(json.dumps(disagreement(), indent=1))
    elif a[:1] == ["readiness"]:
        print(json.dumps(readiness(), indent=1))
    elif a[:1] == ["export"]:
        print(json.dumps(export(), indent=1))
    else:
        print(__doc__)
