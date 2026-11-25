"""Local HTML dashboard: python -m aic.dashboard  ->  dashboard/index.html (gitignored; contains founder data).

One self-contained file: inline CSS/JS, no external requests. All document, research and reply text is
untrusted, so it is embedded as JSON (with '<' escaped) and rendered with textContent only. Links are
created only for http(s) URLs and for local source PDFs.
"""
import json
import re
import sqlite3
from typing import Optional
from datetime import datetime
from pathlib import Path

from . import assurance, config, costs, db, handover, learning
from .ingest import COMPANIES

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "index.html"
DATA = ROOT / "data"


def _load(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _rows(conn, sql, args=()):
    conn.row_factory = sqlite3.Row
    r = [dict(x) for x in conn.execute(sql, args)]
    conn.row_factory = None
    return r


def pdf_link(cite: str) -> str:
    """'Pumpwise/deck p6 (slide 7)' -> '../seed/applications/Pumpwise/deck.pdf#page=6' (local file)."""
    m = re.match(r"^(\w+)/(deck|form) p(\d+)", cite or "")
    return f"../seed/applications/{m.group(1)}/{m.group(2)}.pdf#page={m.group(3)}" if m else ""


def _evidence(items):
    out = []
    for e in items or []:
        out.append({"ref": e.get("ref"), "point": e.get("point"), "quote": e.get("quote"), "type": e.get("type"),
                    "cite": e.get("cite"), "pdf": pdf_link(e.get("cite", "")), "url": e.get("url"),
                    "accessed": e.get("accessed_date"), "published": e.get("published_date"),
                    "confidence": e.get("confidence"), "status": e.get("status")})
    return out


def collect() -> dict:
    cfg = config.load()
    conn = db.connect()
    fund = _load(DATA / "research" / "_fund.json", {"overlaps": []})
    from . import oos
    blinded = oos.blinded_companies(conn)
    companies = []
    for co in COMPANIES + sorted(p.stem for p in (DATA / "scores").glob("*.json") if p.stem not in COMPANIES):
        if co in blinded:
            continue   # out-of-sample test: partners decide before seeing the screener's view
        sc = _load(DATA / "scores" / f"{co}.json")
        if not sc:
            continue
        checks = _load(DATA / "checks" / f"{co}.json", [])
        res = _load(DATA / "research" / f"{co}.json", {"findings": [], "competitors": [], "conflicts": [], "not_found": []})
        app = _load(DATA / "applications" / f"{co}.json", {"form_fields": {}})
        ff = app["form_fields"]
        crit = []
        for k, c in sc["criteria"].items():
            adj = [a for a in sc["adjustments"] if a["criterion"] == k]
            crit.append({"id": k, "name": cfg["criteria"][k]["name"], "weight": c["weight"], "proposed": c["proposed"],
                         "final": c["final"], "points": c["points"], "unknown": c["unknown"],
                         "confidence": c["confidence"], "rationale": c["rationale"], "evidence": _evidence(c["evidence"]),
                         "adjustments": adj, "subparts": {n: {"present": s.get("present"), "normalised": s.get("normalised")}
                                                          for n, s in (c.get("subparts") or {}).items()},
                         "m3": {"public": c.get("public_line_fit"), "observed": c.get("observed_pattern_fit")} if k == "M3" else None,
                         "past": [{"message": p["message"]} for p in sc.get("past_corrections", {}).get(k, [])]})
        gates = [{"id": g, "state": v["state"], "reason": v.get("reason", ""), "evidence": _evidence(v.get("evidence")),
                  "adjacent": v.get("adjacent_overlaps"), "caveat": v.get("caveat")} for g, v in sc["gates"].items()]
        disc = []
        for c in checks:
            if c["status"] == "PASS":
                continue
            st = c.get("stated") or {}
            disc.append({"id": c["id"], "status": c["status"], "kind": c["kind"], "label": c["label"],
                         "stated": st.get("as_written"), "stated_cite": st.get("cite"), "stated_pdf": pdf_link(st.get("cite", "")),
                         "recomputed": c.get("recomputed"), "diff_pct": c.get("diff_pct"), "direction": c.get("direction"),
                         "material": c.get("material_field"), "curated": c.get("curated"), "note": c.get("note"),
                         "inputs": [{"label": i.get("label"), "as_written": i.get("as_written"), "cite": i.get("cite"),
                                     "pdf": pdf_link(i.get("cite", ""))} for i in c.get("inputs", [])]})
        n_pass = sum(c["status"] == "PASS" for c in checks)
        fmap = {f["id"]: f for f in res["findings"]}
        research = {
            "competitors": [{"name": c["name"], "funded": c.get("funded"), "funding": c.get("funding"),
                             "named": c.get("named_in_application"),
                             "links": [{"url": fmap[i]["url"], "publisher": fmap[i]["publisher"],
                                        "accessed": fmap[i]["accessed_date"]} for i in c.get("finding_ids", []) if i in fmap]}
                            for c in res["competitors"]],
            "findings": [{"id": f["id"], "topic": f["topic"], "stance": f["stance"], "claim": f["supports_claim"],
                          "finding": f["finding"], "url": f["url"], "publisher": f["publisher"],
                          "published": f["published_date"], "accessed": f["accessed_date"], "confidence": f["confidence"]}
                         for f in res["findings"]],
            "conflicts": res["conflicts"], "not_found": res["not_found"]}
        history = {
            "outcomes": _rows(conn, "SELECT model_band, model_recommendation, human_decision, decided_by, decided_at, reason, created_at "
                                    "FROM outcomes WHERE company=? ORDER BY id", (co,)),
            "corrections": _rows(conn, "SELECT criterion, model_score, human_score, reason, corrected_by, corrected_at "
                                       "FROM corrections WHERE company=? ORDER BY id", (co,)),
            "outbox": _rows(conn, "SELECT o.id, o.kind, o.status, o.to_addr, o.created_at, o.sent_at, a.approved_by "
                                  "FROM outbox o LEFT JOIN approvals a ON a.id=o.approval_id WHERE o.company=? ORDER BY o.id", (co,)),
            "holds": _rows(conn, "SELECT h.id, h.start_at, h.status, a.approved_by FROM calendar_holds h "
                                 "LEFT JOIN approvals a ON a.id=h.approval_id WHERE h.company=? ORDER BY h.id", (co,)),
            "replies": _rows(conn, "SELECT r.received_at, r.classification, r.confirmed_by, r.action FROM replies r "
                                   "JOIN threads t ON t.id=r.thread_id WHERE t.company=? ORDER BY r.id", (co,)),
        }
        companies.append({
            "company": co, "sector": ff.get("sector_selected", {}).get("value"), "stage": ff.get("stage_selected", {}).get("value"),
            "location": ff.get("location", {}).get("value"), "one_liner": ff.get("one_liner", {}).get("value"),
            "raise": ff.get("raise", {}).get("value"),
            "total": sc["total"], "band": sc["band"], "band_reasons": sc["band_reasons"],
            "subtotals": {"founder": sc["founder_subtotal"], "path": sc["path_subtotal"],
                          "thesis": sc["thesis_subtotal"], "structure": sc["structure_subtotal"]},
            "close_call": sc["close_call"], "close_call_threshold": sc["close_call_threshold"],
            "swing": sc["swing_criteria"], "integrity_cap": sc["integrity_cap"], "unknown": sc["unknown"],
            "routing": sc["routing"], "criteria": crit, "gates": gates, "discrepancies": disc, "checks_passed": n_pass,
            "checks_total": len(checks), "research": research, "history": history,
            "overlaps": [o for o in fund.get("overlaps", []) if o.get("applicant") == co and o.get("portfolio_company")]})
    bt = _load(DATA / "backtest" / "result.json")
    backtest = None
    if bt:
        backtest = {"agreement": bt["agreement"], "rows": [
            {"memo": r["memo_no"], "company": r["company"], "decision": r["decision"], "total": r["total"], "band": r["band"],
             "result": r["result"], "founder": r["founder"], "path": r["path"]} for r in bt["rows"]]}
    return {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "config_version": cfg.get("version"),
            "thresholds": cfg["thresholds"], "groups": {g: sum(cfg["criteria"][k]["weight"] for k in ks)
                                                         for g, ks in cfg["groups"].items()},
            "companies": companies, "blinded": sorted(blinded), "backtest": backtest, "assurance": assurance.build(), "ai_cost": costs.build(), "learning": learning.build(), "handover": handover.build(),
            "reports": sorted(p.name for p in (ROOT / "reports").glob("stage*.md")) + ["trust_and_limits.md", "requirements_audit.md", "production_readiness.md", "feedback_and_finetuning.md", "handover_readiness.md"]}


PUBLISH_HEAD = """<title>AIC Screener</title>
<meta name="claude:viewport-fit-sides" content="cover">
"""


def publishable(data: dict) -> dict:
    """Variant for an online page: no links to local files (source PDFs, reports)."""
    d = json.loads(json.dumps(data))
    for c in d["companies"]:
        for cr in c["criteria"]:
            for e in cr["evidence"]:
                e["pdf"] = ""
        for g in c["gates"]:
            for e in g["evidence"]:
                e["pdf"] = ""
        for x in c["discrepancies"]:
            x["stated_pdf"] = ""
            for i in x["inputs"]:
                i["pdf"] = ""
    d["reports"] = []
    d["backtest"] = None   # names real memo companies with the fund's decisions; kept off the online page
    return strip_portfolio(d)


# Fund programme names kept off the online page (user, 2026-11-19).
FUND_PROGRAMMES = ["TorQLabs", "Golden Ticket"]


def portfolio_names() -> list:
    """Portfolio company names (and short forms) from the fund research, longest first."""
    f = _load(DATA / "research" / "_fund.json", {"portfolio": [], "overlaps": []})
    raw = {p["name"] for p in f.get("portfolio", [])} | {o["portfolio_company"] for o in f.get("overlaps", [])
                                                         if o.get("portfolio_company")}
    names = set()
    for n in raw:
        for part in re.split(r"\s*/\s*", n):
            names.add(part.strip())
            first = part.split()[0] if part.split() else ""
            if len(part.split()) > 1 and len(first) >= 4 and first[0].isupper() and first not in ("Grid", "Giga", "Spill", "Hectar"):
                names.add(first)          # e.g. 'Wint', 'Karban', 'PierSight', 'MeetRecord'
    names |= {"Giva", "GIVA", "Outdoo", "Hectar Global", "Grid OS"}
    return sorted((n for n in names if n), key=len, reverse=True)


def strip_portfolio(d: dict) -> dict:
    """Online page: no portfolio companies, overlap details or fund-research evidence."""
    pat = re.compile(r"(?<![\w&])(" + "|".join(re.escape(n) for n in portfolio_names()) + r")(?![\w])")

    prog = re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in FUND_PROGRAMMES) + r")(?![\w])")

    def scrub(x):
        if isinstance(x, str):
            return prog.sub("[fund programme]", pat.sub("[portfolio company]", x))
        if isinstance(x, list):
            return [scrub(i) for i in x]
        if isinstance(x, dict):
            return {k: scrub(v) for k, v in x.items()}
        return x

    for c in d["companies"]:
        c["overlaps"] = []
        for cr in c["criteria"]:
            cr["evidence"] = [e for e in cr["evidence"] if not str(e.get("ref", "")).startswith("research:_fund:")]
        for g in c["gates"]:
            g["evidence"] = [e for e in g["evidence"] if not str(e.get("ref", "")).startswith("research:_fund:")]
            if g["id"] == "G1":
                g["reason"] = ("Direct overlap with a portfolio company (named on the internal dashboard only)"
                               if g["state"] == "hold" else "No direct portfolio overlap found")
                g["adjacent"], g["caveat"] = None, None
    return scrub(d)


def render(data: dict, publish: bool = False, strip: Optional[bool] = None, base: str = "../") -> str:
    """publish: page for the artifact host (no skeleton, host theme). strip: the trimmed online variant
    (no local links, backtest or portfolio detail); defaults to `publish` for backward compatibility.
    base: prefix for source-PDF and report links ('../' locally, '' when the files ship beside the page)."""
    strip = publish if strip is None else strip
    if strip:
        data = publishable(data)
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    payload = payload.replace("../seed/applications/", base + "seed/applications/")
    html = TEMPLATE.replace("__DATA__", payload).replace('"../reports/"+r', json.dumps(base + "reports/") + "+r")
    if publish:
        # The artifact host supplies doctype/head/body and the theme; keep page content, style and scripts.
        head_end = html.index("<style>")
        html = PUBLISH_HEAD + html[head_end:]
        html = html.replace("</style></head>\n<body>", "</style>").replace("</script></body></html>", "</script>")
        html = re.sub(r"<!--theme-->.*?<!--/theme-->", "", html, flags=re.S)
        html = re.sub(r"// ---- theme toggle.*?// ---- end theme toggle\n", "", html, flags=re.S)
    return html


PUBLISH_OUT = ROOT / "dashboard" / "publish.html"
SITE = ROOT / "site"


def companion_files() -> dict:
    """Published path -> local file: source PDFs and reports that the full page links to."""
    files = {}
    for co in COMPANIES:
        for doc in ("deck", "form"):
            f = ROOT / "seed" / "applications" / co / f"{doc}.pdf"
            if f.exists():
                files[f"seed/applications/{co}/{doc}.pdf"] = f
    for f in sorted((ROOT / "reports").glob("*.md")):
        files[f"reports/{f.name}"] = f
    return files


def build(mode: str = "local") -> Path:
    """local: dashboard/index.html (links ../). artifact: dashboard/publish.html, full content, files beside it.
    trimmed: dashboard/publish.html, the earlier stripped variant. site: site/ for static hosting (Vercel)."""
    import shutil
    data = collect()
    if mode == "local":
        out, html = OUT, render(data)
    elif mode == "artifact":
        out, html = PUBLISH_OUT, render(data, publish=True, strip=False, base="")
    elif mode == "trimmed":
        out, html = PUBLISH_OUT, render(data, publish=True, strip=True)
    elif mode == "site":
        if SITE.exists():
            shutil.rmtree(SITE)
        out, html = SITE / "index.html", render(data, base="")
        for rel, src in companion_files().items():
            (SITE / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, SITE / rel)
    else:
        raise ValueError(mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


TEMPLATE = (Path(__file__).resolve().parent / "dashboard_template.html").read_text()

if __name__ == "__main__":
    import sys
    mode = next((a[2:] for a in sys.argv[1:] if a.startswith("--")), "local")
    print(build({"publish": "artifact"}.get(mode, mode)))
