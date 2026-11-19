"""Stage 4: scoring. The model proposes; code validates, applies rubric rules, and computes every number.

Model output: data/scores/raw/<Company>.json (see prompts/score.md).
Code output: data/scores/<Company>.json, plus an undecided row in the outcomes table (a human decides).

Order of operations (all in code):
 1. Validate: every criterion present, integer 0-5, evidence present unless unknown, every evidence ref resolves,
    quotes found in the referenced source, T2 equals its disclosed sub-parts, rubric anchors respected.
 2. Caps (logged as adjustments): founder evidence cap, then pedigree cap.
 3. Gates: G1 (portfolio, from research), G2c (sector), G3 (stage) in code; G2a, G2b, G4, G5 from the model with evidence.
 4. Points, subtotals, total; band; integrity cap; close call; routing.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, text

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "scores" / "raw"
OUT = ROOT / "data" / "scores"
CRITERIA = ["F1", "F2", "F3", "F4", "T1", "T2", "T3", "M1", "M2", "M3", "S1", "S2"]
MODEL_GATES = ["G2a", "G2b", "G4", "G5"]
FIT = {"fit", "partial", "outside"}


class ScoreError(ValueError):
    pass


# ---- evidence resolution ----------------------------------------------------
class Sources:
    """Everything a score may cite for one subject (an application, or a blind memo in Stage 5)."""

    def __init__(self, company: str, memo: Optional[dict] = None):
        self.company = company
        self.memo = memo
        self.claims, self.checks, self.research, self.fund, self.form = {}, {}, {}, {}, {}
        if memo is None:
            d = ROOT / "data"
            self.claims = {c["id"]: c for c in json.loads((d / "claims" / f"{company}.json").read_text())["claims"]}
            self.checks = {c["id"]: c for c in json.loads((d / "checks" / f"{company}.json").read_text())}
            rp = d / "research" / f"{company}.json"
            self.research_rec = json.loads(rp.read_text()) if rp.exists() else {"findings": []}
            self.research = {f["id"]: f for f in self.research_rec["findings"]}
            fp = d / "research" / "_fund.json"
            self.fund_rec = json.loads(fp.read_text()) if fp.exists() else {"findings": [], "overlaps": []}
            self.fund = {f["id"]: f for f in self.fund_rec["findings"]}
            self.form = json.loads((d / "applications" / f"{company}.json").read_text())["form_fields"]
            self.docs = {"deck": text.load(f"{company}/deck"), "form": text.load(f"{company}/form")}

    def resolve(self, ref: str) -> dict:
        kind, _, key = ref.partition(":")
        if kind == "claim" and key in self.claims:
            c = self.claims[key]
            return {"type": "document", "cite": c.get("cite"), "text": c["quote"], "as_written": c["as_written"]}
        if kind == "check" and key in self.checks:
            c = self.checks[key]
            cites = [i.get("cite") for i in c.get("inputs", []) if i.get("cite")]
            if c.get("stated") and c["stated"].get("cite"):
                cites.insert(0, c["stated"]["cite"])
            return {"type": "check", "cite": "; ".join(dict.fromkeys(cites)), "status": c["status"],
                    "text": f"{c['label']} {c.get('note', '')} {c.get('direction', '')}"}
        if kind == "research":
            src, fid = (self.fund, key.split(":", 1)[1]) if key.startswith("_fund:") else (self.research, key)
            if fid in src:
                f = src[fid]
                return {"type": "external", "url": f["url"], "accessed_date": f["accessed_date"],
                        "published_date": f["published_date"], "confidence": f["confidence"],
                        "cite": f"{f['publisher']}, {f['published_date']}",
                        "text": f"{f['finding']} {f.get('quote', '')}", "topic": f["topic"], "stance": f["stance"]}
        if kind == "form" and key in self.form:
            f = self.form[key]
            return {"type": "document", "cite": f.get("cite") or f"{self.company}/form p{f['page']}", "text": f["value"]}
        if kind == "memo" and self.memo and self.memo["sections"].get(key):
            return {"type": "document", "cite": f"{self.memo['anon_id']} {key}", "text": self.memo["sections"][key]}
        raise ScoreError(f"evidence ref does not resolve: {ref}")


# ---- validation -------------------------------------------------------------
def material_contradictions(src: Sources) -> List[dict]:
    return [c for c in src.checks.values() if c["status"] == "FAIL" and c["kind"] == "cross_document"
            and c.get("material_field")]


def market_failures(src: Sources) -> List[dict]:
    return [c for c in src.checks.values() if c["status"] == "FAIL"
            and (c["id"].startswith("market.") or c["kind"] == "assumption_vs_observed")]


def _check_evidence(crit: str, items: list, src: Sources, errs: list) -> List[dict]:
    out = []
    for e in items or []:
        try:
            r = src.resolve(e.get("ref", ""))
        except ScoreError as x:
            errs.append(f"{crit}: {x}")
            continue
        if e.get("quote") and text.squash(e["quote"]) not in text.squash(r["text"]):
            errs.append(f"{crit}: quote not found in {e['ref']}")
        out.append({**e, **{k: v for k, v in r.items() if k != "text"}})
    return out


def validate(raw: dict, src: Sources, cfg: dict) -> Tuple[List[str], Dict[str, dict]]:
    errs: List[str] = []
    crits = raw.get("criteria", {})
    resolved: Dict[str, dict] = {}
    for k in CRITERIA:
        c = crits.get(k)
        if c is None:
            errs.append(f"{k}: missing")
            continue
        s = c.get("score")
        if not isinstance(s, int) or not 0 <= s <= 5:
            errs.append(f"{k}: score must be an integer 0-5")
            continue
        if c.get("unknown") and s != 0:
            errs.append(f"{k}: unknown criteria must score 0")
        if not c.get("rationale"):
            errs.append(f"{k}: rationale missing")
        if c.get("confidence") not in ("high", "medium", "low"):
            errs.append(f"{k}: confidence must be high/medium/low")
        ev = _check_evidence(k, c.get("evidence"), src, errs)
        if s > 0 and not ev:
            errs.append(f"{k}: score {s} has no resolvable evidence")
        resolved[k] = {**c, "evidence": ev}
    t2 = crits.get("T2") or {}
    subs = t2.get("subparts") or {}
    names = cfg["criteria"]["T2"]["subparts"]
    if set(subs) != set(names):
        errs.append(f"T2: subparts must be exactly {names}")
    else:
        present = 0
        for n in names:
            sp = subs[n]
            sp_ev = _check_evidence(f"T2.{n}", sp.get("evidence"), src, errs)
            if sp.get("present") and not sp_ev:
                errs.append(f"T2.{n}: marked present without evidence")
            present += bool(sp.get("present"))
            resolved.setdefault("T2", {}).setdefault("subparts", {})[n] = {**sp, "evidence": sp_ev}
        if isinstance(t2.get("score"), int) and t2["score"] != present:
            errs.append(f"T2: score {t2['score']} != {present} sub-parts present (1 point each)")
    m3 = crits.get("M3") or {}
    for f in ("public_line_fit", "observed_pattern_fit"):
        if m3.get(f) not in FIT:
            errs.append(f"M3: {f} must be one of {sorted(FIT)}")
    # rubric anchors (reject, do not silently change)
    if src.memo is None:
        ar = cfg["anchor_rules"]
        mc = material_contradictions(src)
        if mc and isinstance(crits.get("S2", {}).get("score"), int) and crits["S2"]["score"] > ar["S2_max_if_material_contradiction"]:
            errs.append(f"S2: anchor says max {ar['S2_max_if_material_contradiction']} with a material contradiction "
                        f"({', '.join(c['id'] for c in mc)})")
        mf = market_failures(src)
        if mf and isinstance(crits.get("M1", {}).get("score"), int) and crits["M1"]["score"] > ar["M1_max_if_market_or_assumption_check_fails"]:
            errs.append(f"M1: anchor says max {ar['M1_max_if_market_or_assumption_check_fails']} when a market or "
                        f"assumption check fails ({', '.join(c['id'] for c in mf)})")
    gates = raw.get("gates", {})
    for g in MODEL_GATES:
        x = gates.get(g)
        if not x or x.get("state") not in ("clear", "flag"):
            errs.append(f"gate {g}: state must be clear or flag")
            continue
        gev = _check_evidence(f"gate {g}", x.get("evidence"), src, errs)
        if x["state"] == "flag" and not gev:
            errs.append(f"gate {g}: flag without evidence")
        resolved[f"gate:{g}"] = {**x, "evidence": gev}
    return errs, resolved


# ---- rules, totals, bands ------------------------------------------------------
def apply_caps(scores: Dict[str, int], src: Sources, cfg: dict) -> Tuple[Dict[str, int], List[dict]]:
    final, adj = dict(scores), []
    fc = cfg["founder_evidence_cap"]
    supported = any(f["topic"] == "founder" and f["stance"] == "supports" for f in src.research.values())
    if not supported:
        for k in fc["criteria"]:
            if final[k] > fc["max_without_external_support"]:
                adj.append({"criterion": k, "from": final[k], "to": fc["max_without_external_support"],
                            "rule": "founder_evidence_cap: no outside source confirms the founder evidence"})
                final[k] = fc["max_without_external_support"]
    pc = cfg["pedigree_cap"]
    if final[pc["criterion"]] > pc["max_score"] and not any(final[k] >= pc["unless_min_score"] for k in pc["unless_any_of"]):
        adj.append({"criterion": pc["criterion"], "from": final[pc["criterion"]], "to": pc["max_score"],
                    "rule": f"pedigree_cap: {pc['criterion']} max {pc['max_score']} unless "
                            f"{' or '.join(pc['unless_any_of'])} >= {pc['unless_min_score']}"})
        final[pc["criterion"]] = pc["max_score"]
    return final, adj


def code_gates(src: Sources, cfg: dict) -> Dict[str, dict]:
    g = {}
    holds = [o for o in src.fund_rec.get("overlaps", [])
             if o.get("applicant") == src.company and o.get("portfolio_company")
             and o.get("strength") in cfg["gates"]["G1"]["hold_on_strength"]]
    adjacent = [o for o in src.fund_rec.get("overlaps", [])
                if o.get("applicant") == src.company and o.get("portfolio_company") and o not in holds]
    g["G1"] = {"state": "hold" if holds else "clear",
               "reason": "; ".join(f"{o['portfolio_company']}: {o['basis']}" for o in holds) or "no direct overlap found",
               "evidence": [{"ref": f"research:_fund:{i}", **src.resolve(f"research:_fund:{i}")} for o in holds
                            for i in o.get("finding_ids", [])[:2]],
               "adjacent_overlaps": [o["portfolio_company"] for o in adjacent],
               "caveat": "public portfolio list only; the full list is not in the data"}
    sector = src.form.get("sector_selected", {}).get("value", "")
    in_public = any(s in sector.lower() for s in cfg["public_sectors"])
    g["G2c"] = {"state": "clear" if in_public else "flag",
                "reason": f"form sector '{sector}' " + ("is in" if in_public else "is outside") + " the public sector line",
                "evidence": [{"ref": "form:sector_selected", **src.resolve("form:sector_selected")}]}
    stage = src.form.get("stage_selected", {}).get("value", "")
    early = stage.lower() in cfg["pre_seed_stages"]
    g["G3"] = {"state": "clear" if early else "flag", "reason": f"form stage '{stage}'",
               "evidence": [{"ref": "form:stage_selected", **src.resolve("form:stage_selected")}]}
    return g


def band_for(total: float, gates: Dict[str, dict], material: bool, cfg: dict) -> Tuple[str, List[str]]:
    why = []
    t = cfg["thresholds"]
    if any(x["state"] == "hold" for x in gates.values()):
        return "hold", ["a gate is on Hold"]
    band = "call" if total >= t["call"] else "partner_review" if total >= t["pass"] else "pass"
    why.append(f"score band: {band}")
    flags = [k for k, x in gates.items() if x["state"] == "flag"]
    if flags and band == "call":
        band = cfg.get("flag_at_call_band", "partner_review")
        why.append(f"open flag(s) {', '.join(flags)}: lowered to partner review")
    elif flags and band == "pass":
        band = cfg.get("flag_below_pass", "pass")
        why.append(f"open flag(s) {', '.join(flags)}: pass recommendation with flag attached; partner decides")
    elif flags:
        why.append(f"open flag(s) {', '.join(flags)}: partner review")
    if material and band == "call":
        band = cfg["integrity_cap"]["max_band"]
        why.append("integrity cap: material contradiction unresolved")
    return band, why


def close_call(total: float, cfg: dict) -> Optional[int]:
    t = cfg["thresholds"]
    for th in (t["call"], t["pass"]):
        if abs(total - th) <= t["close_call_margin"]:
            return th
    return None


def swing_criteria(final: Dict[str, int], resolved: dict, cfg: dict, threshold: Optional[int], total: float) -> List[dict]:
    """The two criteria most likely to change the outcome: weakest-evidenced, highest-weight criteria
    that still have room to move in the direction of the nearest threshold."""
    t = cfg["thresholds"]
    target = threshold if threshold is not None else min((t["call"], t["pass"]), key=lambda x: abs(total - x))
    up = target > total
    conf_rank = {"low": 0, "medium": 1, "high": 2}
    cands = []
    for k in CRITERIA:
        room = (5 - final[k]) if up else final[k]
        if room == 0:
            continue
        w = cfg["criteria"][k]["weight"]
        unk = bool(resolved[k].get("unknown"))
        cands.append((conf_rank.get(resolved[k].get("confidence"), 0) - (1 if unk else 0), -w, k, room, w))
    cands.sort()
    return [{"criterion": k, "weight": w, "points_per_step": w / 5, "direction": "up" if up else "down",
             "why": "unknown (missing data)" if resolved[k].get("unknown") else f"{resolved[k].get('confidence')} confidence"}
            for _, _, k, room, w in cands[:2]]


def routing(src: Sources, band: str) -> List[str]:
    sector = src.form.get("sector_selected", {}).get("value", "").lower() if src.form else ""
    r = ["Kushal sees the outcome before anything is decided; nobody is auto-rejected or auto-advanced."]
    if "deeptech" in sector:
        r.append("Deeptech: Aditya does the second call himself.")
    elif any(s in sector for s in ("fintech", "consumer")):
        r.append("Fintech/consumer: Riya may run the first screen; Kushal gates the outcome.")
    if band == "hold":
        r.append("Hold: no outreach until Kushal resolves the portfolio conflict.")
    elif band == "call":
        r.append("Call band: Kushal sees the outcome before any email; Riya reviews the draft.")
    elif band == "partner_review":
        r.append("Partner review: no email by default.")
    else:
        r.append("Pass recommendation: partner decides; draft note only.")
    return r


def score(company: str, raw: Optional[dict] = None, cfg: Optional[dict] = None, memo: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    raw = raw if raw is not None else json.loads((RAW / f"{company}.json").read_text())
    src = Sources(company, memo)
    errs, resolved = validate(raw, src, cfg)
    if errs:
        raise ScoreError(f"{company}: " + " | ".join(errs))
    proposed = {k: raw["criteria"][k]["score"] for k in CRITERIA}
    t2_adj = normalise_t2(resolved, src, cfg, proposed) if memo is None else []
    final, adjustments = apply_caps(proposed, src, cfg) if memo is None else apply_caps_memo(proposed, cfg)
    adjustments = t2_adj + adjustments
    pts = {k: cfg["criteria"][k]["weight"] * final[k] / 5 for k in CRITERIA}
    groups = {g: round(sum(pts[k] for k in ks), 2) for g, ks in cfg["groups"].items()}
    total = round(sum(pts.values()), 2)
    gates = {}
    if memo is None:
        gates.update(code_gates(src, cfg))
    for g in MODEL_GATES:
        gates[g] = resolved[f"gate:{g}"]
    material = material_contradictions(src) if memo is None else []
    band, why = band_for(total, gates, bool(material), cfg)
    cc = close_call(total, cfg)
    out = {
        "company": company, "total": total, "band": band, "band_reasons": why,
        "founder_subtotal": groups["founder"], "path_subtotal": groups["path"],
        "thesis_subtotal": groups["thesis"], "structure_subtotal": groups["structure"],
        "close_call": cc is not None, "close_call_threshold": cc,
        "swing_criteria": swing_criteria(final, resolved, cfg, cc, total),
        "integrity_cap": {"applies": bool(material), "contradictions": [
            {"id": c["id"], "field": c["material_field"], "label": c["label"]} for c in material]},
        "gates": gates,
        "criteria": {k: {"proposed": proposed[k], "final": final[k], "points": round(pts[k], 2),
                         "weight": cfg["criteria"][k]["weight"], "unknown": bool(resolved[k].get("unknown")),
                         "confidence": resolved[k].get("confidence"), "rationale": resolved[k].get("rationale"),
                         "evidence": resolved[k]["evidence"],
                         **({"subparts": resolved["T2"]["subparts"]} if k == "T2" else {}),
                         **({"public_line_fit": raw["criteria"]["M3"]["public_line_fit"],
                             "observed_pattern_fit": raw["criteria"]["M3"]["observed_pattern_fit"]} if k == "M3" else {})}
                     for k in CRITERIA},
        "adjustments": adjustments,
        "unknown": [k for k in CRITERIA if resolved[k].get("unknown")],
        "routing": routing(src, band) if memo is None else [],
        "config_version": cfg.get("version"),
    }
    return out


def normalise_t2(resolved: dict, src: Sources, cfg: dict, proposed: Dict[str, int]) -> List[dict]:
    """Apply T2 sub-part rules uniformly (config t2_rules). Changes proposed['T2'] in place; returns adjustments."""
    rules = cfg.get("t2_rules") or {}
    adj = []
    n = rules.get("cac_by_channel_min_channels")
    if n:
        chans = {(c.get("entity") or "").strip().lower() for c in src.claims.values()
                 if c.get("metric") == "cac_channel_inr" and c.get("valid") and c.get("value") is not None}
        chans.discard("")
        code_present = len(chans) >= n
        sp = resolved["T2"]["subparts"]["cac_by_channel"]
        if bool(sp.get("present")) != code_present:
            sp["present"] = code_present
            sp["normalised"] = f"{len(chans)} channel CAC figure(s) disclosed; rule needs >= {n}"
            new = sum(bool(x.get("present")) for x in resolved["T2"]["subparts"].values())
            if new == 0:
                resolved["T2"]["unknown"] = True   # no sub-part disclosed: missing data, scored 0
            adj.append({"criterion": "T2", "from": proposed["T2"], "to": new,
                        "rule": f"t2_rules.cac_by_channel_min_channels={n} {sp['normalised']}"})
            proposed["T2"] = new
    return adj


def apply_caps_memo(scores: Dict[str, int], cfg: dict):
    """Memos are partner write-ups, not applications: only the pedigree cap applies (no outside-evidence cap)."""
    final, adj = dict(scores), []
    pc = cfg["pedigree_cap"]
    if final[pc["criterion"]] > pc["max_score"] and not any(final[k] >= pc["unless_min_score"] for k in pc["unless_any_of"]):
        adj.append({"criterion": pc["criterion"], "from": final[pc["criterion"]], "to": pc["max_score"], "rule": "pedigree_cap"})
        final[pc["criterion"]] = pc["max_score"]
    return final, adj


def record_outcome(conn, result: dict) -> int:
    rec = {"call": "Move to call", "partner_review": "Partner review", "pass": "Pass recommendation", "hold": "Hold"}
    return conn.execute(
        "INSERT INTO outcomes (company, model_band, model_recommendation) VALUES (?, ?, ?)",
        (result["company"], result["band"], f"{rec[result['band']]} ({result['total']})")).lastrowid


def main(companies: List[str]) -> List[dict]:
    from . import db
    OUT.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    results = []
    from . import feedback
    cfg = config.load()
    for co in companies:
        r = score(co, cfg=cfg)
        r["sector"] = feedback.company_sector(co, cfg)
        r["past_corrections"] = feedback.surface(conn, co, r["sector"])   # same sector, other companies
        (OUT / f"{co}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
        # One undecided outcome per company: refresh the model's view; never touch a human decision.
        conn.execute("DELETE FROM outcomes WHERE company=? AND human_decision IS NULL", (co,))
        record_outcome(conn, r)
        results.append(r)
    conn.commit()
    return results


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        cfg = config.load()
        raw = json.loads((RAW / f"{sys.argv[2]}.json").read_text())
        errs, _ = validate(raw, Sources(sys.argv[2]), cfg)
        print(f"{sys.argv[2]}: {len(errs)} errors")
        for e in errs:
            print("  ", e)
        sys.exit(1 if errs else 0)
    from .ingest import COMPANIES
    for r in main(COMPANIES):
        print(f"{r['company']:11} {r['total']:6.1f} F={r['founder_subtotal']:5.1f} P={r['path_subtotal']:5.1f} "
              f"{r['band']:15} close={r['close_call']} cap={r['integrity_cap']['applies']}")
