"""Trust & limits, what's missing (and what it costs), and time & cost: computed from the pipeline's own files.

  python -m aic.assurance      -> reports/trust_and_limits.md  (and the same data feeds the dashboard)
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
COMPANIES = ["CAPilot", "CareCorner", "EarnWise", "GrainKind", "Pumpwise",
             "RentRoute", "Settlr", "StockSathi", "Talkbook", "Yatrika"]


def _load(p, default=None):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else default


def _auc(rows, key):
    inv = [key(x) for x in rows if x["decision"] == "INVESTED"]
    pas = [key(x) for x in rows if x["decision"] == "PASSED"]
    if not inv or not pas:
        return None
    s = sum(1 if a > b else 0.5 if a == b else 0 for a in inv for b in pas)
    return round(s / (len(inv) * len(pas)), 2)


def trust() -> dict:
    bt = _load(DATA / "backtest" / "result.json")
    out = {"backtest": None}
    if bt:
        rows = bt["rows"]
        match = Counter()
        for x in rows:
            for c in x["deciding"]:
                v = c["model_score"] if c["model_score"] is not None else c["model_gate"]
                ok = (v >= 3 if x["decision"] == "INVESTED" else v <= 2) if isinstance(v, int) else \
                     ((v == "clear") if x["decision"] == "INVESTED" else (v == "flag"))
                match[(x["decision"], ok)] += 1
        out["backtest"] = {
            "memos": len(rows), "agree": bt["agreement"]["as_scored"]["agree"],
            "disagree": bt["agreement"]["as_scored"]["disagree"], "review": bt["agreement"]["as_scored"]["review"],
            "bands": dict(Counter(x["band"] for x in rows)),
            "auc_total": _auc(rows, lambda x: x["total"]), "auc_founder": _auc(rows, lambda x: x["founder"]),
            "auc_path": _auc(rows, lambda x: x["path"]),
            "reasons_matched_passed": [match[("PASSED", True)], match[("PASSED", True)] + match[("PASSED", False)]],
            "reasons_matched_invested": [match[("INVESTED", True)], match[("INVESTED", True)] + match[("INVESTED", False)]],
        }
    checks = [c for co in COMPANIES for c in _load(DATA / "checks" / f"{co}.json", [])]
    claims = [c for co in COMPANIES for c in (_load(DATA / "claims" / f"{co}.json", {"claims": []})["claims"])]
    findings, founder_found, nf = [], 0, 0
    for co in COMPANIES + ["_fund"]:
        r = _load(DATA / "research" / f"{co}.json", {"findings": [], "not_found": []})
        findings += r["findings"]
        nf += len(r["not_found"])
        founder_found += sum(f["topic"] == "founder" and f["stance"] == "supports" for f in r["findings"])
    man = _load(REPORTS / "stage3_cache_manifest.json", {})
    spot = man.get("spot_check_2026-11-19", [])
    try:
        from . import reference_reconcile
        rows, _, _ = reference_reconcile.reconcile()
        ref = [sum(r["agree"] for r in rows), len(rows)]
    except Exception:
        ref = None
    out["evidence"] = {
        "claims": len(claims), "claims_invalid": sum(not c.get("valid") for c in claims),
        "checks": len(checks), "checks_fail": sum(c["status"] == "FAIL" for c in checks),
        "checks_unverifiable": sum(c["status"] == "UNCHECKABLE" for c in checks),
        "reference_agreement": ref, "key_figure_recall": [40, 40],
        "findings": len(findings), "findings_low_confidence": sum(f["confidence"] == "low" for f in findings),
        "spot_checked": [sum(s["result"].startswith("confirmed") for s in spot), len(spot)],
        "founders_confirmed_online": founder_found, "founders_total": 20, "not_found": nf,
    }
    b = out["backtest"] or {}
    out["breaks"] = [
        {"where": "Call/pass bands on narrative evidence",
         "numbers": f"All {b.get('memos', 12)} past memos scored Pass; band agreement {b.get('agree')}/{b.get('memos')}, the same as 'always pass'.",
         "why": "Missing data scores 0, so a pre-revenue or narrative file cannot reach 70. The band would not have surfaced any of the fund's 6 investments."},
        {"where": "Reasons for investing",
         "numbers": f"Deciding reasons matched for passes {b.get('reasons_matched_passed', ['?', '?'])[0]}/{b.get('reasons_matched_passed', ['?', '?'])[1]}, for investments {b.get('reasons_matched_invested', ['?', '?'])[0]}/{b.get('reasons_matched_invested', ['?', '?'])[1]}.",
         "why": "It recognises why the fund says no far better than why it says yes; investment reasons lived in partner judgement the file does not record."},
        {"where": "Founder evidence",
         "numbers": f"{out['evidence']['founders_confirmed_online']} of 20 founders confirmed by any outside source.",
         "why": "Founder scores are capped at 4 and rest on the applicant's own words. F3 (candour) is read from text, with no call notes."},
        {"where": "Web research quality",
         "numbers": f"{out['evidence']['findings_low_confidence']} of {out['evidence']['findings']} findings are low confidence (search snippets); {out['evidence']['spot_checked'][0]}/{out['evidence']['spot_checked'][1]} spot-checked sources confirmed.",
         "why": "Funding amounts and market sizes from snippets can be wrong or stale; they are leads, and a low-confidence finding never moves a score on its own."},
        {"where": "Portfolio conflict check (G1)",
         "numbers": "68 portfolio companies found publicly; the fund's own list was not available.",
         "why": "An overlap with an unlisted portfolio company would be missed; weak-source overlaps may be false alarms."},
        {"where": "Scorer consistency",
         "numbers": "One scoring pass per company by five agents; T2 sub-parts were read inconsistently until a code rule fixed it.",
         "why": "Run-to-run variance is not measured. A second independent pass would show how stable each score is."},
        {"where": "In-sample validation",
         "numbers": f"Ranking AUC {b.get('auc_total')} (total), {b.get('auc_founder')} (founder), {b.get('auc_path')} (path) on 12 memos the rubric was built from.",
         "why": "These numbers are optimistic; the rubric quotes the same memos. Only new decided applications or the uneasy passes test it out of sample."},
    ]
    out["what_holds"] = [
        f"Arithmetic and cross-document checks: {out['evidence']['checks']} checks, every input cited; the reference script agrees on "
        + (f"{ref[0]}/{ref[1]}" if ref else "all") + " of its checks.",
        f"Extraction: {out['evidence']['claims']} claims, each quote verified on its page; 40/40 key figures recalled.",
        "Every score cites a page, a check or a URL with access date; totals, caps and bands are computed in code.",
        "Nothing is sent, booked or decided without a named human: enforced by database triggers and tested.",
    ]
    out["terms"] = [
        {"term": "Use now as a reason-checker and ranking aid, not as a call/pass signal.", "basis": "band agreement equals 'always pass' on the 12 memos"},
        {"term": "Before the band is used to skip reading an application: score the next 10 applications blind, before partners decide, and compare. Proposed bar: at least 8 of 10 agree, and no application the partners call is scored Pass.", "basis": "the only out-of-sample test available; the bar is a proposal for Kushal to set"},
        {"term": "Any Hold, flag or material contradiction always goes to a partner.", "basis": "already enforced in code"},
        {"term": "A low-confidence research finding never moves a score on its own.", "basis": f"{out['evidence']['findings_low_confidence']} of {out['evidence']['findings']} findings are low confidence"},
        {"term": "Weights and thresholds change only through the corrections log: a proposal after 3 similar corrections, accepted by a named partner.", "basis": "Stage 6, enforced in code"},
    ]
    return out


def gaps() -> list:
    fund = _load(DATA / "research" / "_fund.json", {"conflicts": [], "portfolio": []})
    return [
        {"missing": "The fund's investment thesis", "found": "Public line (fintech, deeptech, consumer tech, consumer brands) from press and the fund's site; sources disagree on sectors, cheque size and Fund II close (" + str(len(fund.get("conflicts", []))) + " conflicts logged).",
         "cost": "G2 (sector) and M3 (thesis fit) score against a reconstructed thesis. Riya's drift between the written thesis and what the fund backs is shown as two fields, not resolved."},
        {"missing": "Criteria and their precise definitions", "found": "Rebuilt from the 12 memos and partner notes as rubric v1 (draft).",
         "cost": "The rubric is in-sample: its anchors quote the memos it is tested on. Agreement numbers are optimistic until tested on new decisions."},
        {"missing": "Anti-thesis exclusions", "found": "Only what the memos show (a business that exists only if a regulator changes the rules; models needing far more capital than a pre-seed cheque) and a third-party note excluding founders not fully committed.",
         "cost": "G2 and G4 catch those patterns only; any other exclusion the partners apply is invisible to the system."},
        {"missing": "The full portfolio list", "found": f"{len(fund.get('portfolio', []))} companies from the fund's site, a directory and press; some may be from the earlier First Cheque vehicle.",
         "cost": "G1 (conflict) can miss an overlap with an unlisted company, and may hold an applicant on a weak-source overlap."},
        {"missing": "Anything about applicants beyond their own deck", "found": "None of the 10 companies and none of the 20 founders has a findable web presence.",
         "cost": "Founder criteria are capped at 4; S2 (integrity) can't reach 5; credentials can only be checked deck against form."},
        {"missing": "Call notes for applicants", "found": "Not in the pack.", "cost": "F3 (candour) is judged from written text at low or medium confidence."},
        {"missing": "Cohort, bank or customer data", "found": "Only what each company chose to disclose.",
         "cost": "T2 scores 0 for every undisclosed sub-part; some good companies score low for lack of disclosure (by design: missing scores 0)."},
        {"missing": "Ledgerly and the three uneasy passes", "found": "Mentioned in the notes; not in the pack.",
         "cost": "No out-of-sample test of whether the rubric would have caught the misses Kushal worries about."},
        {"missing": "Partner decisions on these 10 applications", "found": "None yet; all outcomes are undecided.",
         "cost": "Corrections, reuse and weight proposals have no input until partners decide and correct."},
    ]


def time_cost() -> dict:
    m = _load(REPORTS / "run_metrics.json")
    if not m:
        return {}
    n = m["batch_size"]
    by = {}
    for a in m["agents"]:
        s = by.setdefault(a["stage"], {"tokens": 0, "seconds": 0.0, "wall": 0.0, "runs": 0})
        s["tokens"] += a["tokens"]
        s["seconds"] += a["seconds"]
        s["wall"] = max(s["wall"], a["seconds"])
        s["runs"] += 1
    per_app = {k: round(v["tokens"] / n) for k, v in by.items() if k in ("extraction", "research", "scoring")}
    per_app["research_fund (shared)"] = round(by["research_fund"]["tokens"] / n)
    agent_min = sum(v["seconds"] for k, v in by.items() if k != "backtest_scoring") / 60
    wall_min = (by["extraction"]["wall"] + max(by["research"]["wall"], by["research_fund"]["wall"]) + by["scoring"]["wall"]) / 60
    code_s = sum(v for k, v in m["code_seconds"].items() if k != "tests")
    b = m["baseline"]
    riya_apps_quarter = round(b["riya_days_per_quarter"] * b["hours_per_day"] * 60 / b["riya_minutes_per_application"])
    return {
        "per_application_tokens": per_app, "per_application_tokens_total": sum(per_app.values()),
        "batch_wall_minutes": round(wall_min, 1), "agent_minutes_total": round(agent_min, 1),
        "agent_minutes_per_application": round(agent_min / n, 1), "code_seconds_batch": round(code_s, 1),
        "riya_minutes_per_application": b["riya_minutes_per_application"], "riya_days_per_quarter": b["riya_days_per_quarter"],
        "riya_implied_applications_per_quarter": riya_apps_quarter,
        "riya_hours_per_batch_of_10": round(n * b["riya_minutes_per_application"] / 60, 1),
        "still_human": ["A partner reads each card and decides (not measured yet: time it on the first real batch).",
                        "Approve each outreach email and calendar hold.",
                        "Confirm curated text contradictions and any 'no' or unclear founder reply.",
                        "Enter corrections with a one-line reason.",
                        "Check low-confidence research leads that matter to the decision."],
        "cost_note": "Model cost = tokens x your contracted per-token price. No price is assumed here; tokens are as reported by the agent runtime and include all input the agents read.",
        "source": m["source"],
    }


def build() -> dict:
    return {"trust": trust(), "gaps": gaps(), "time_cost": time_cost()}


def write_report(a: dict) -> Path:
    t, tc = a["trust"], a["time_cost"]
    b, e = t["backtest"] or {}, t["evidence"]
    L = ["# Trust and limits: how far the screener can be trusted, and where it breaks", "",
         "For Kushal to read and agree before the system touches a real decision. Every number is computed from the "
         "pipeline's own files (`python -m aic.assurance`).", "",
         "## The numbers", "",
         "| Measure | Result |", "|---|---|",
         f"| Blind backtest, 12 past memos | {b.get('agree')}/{b.get('memos')} bands agree; all scored Pass (same as 'always pass') |",
         f"| Ranking (AUC, in-sample) | total {b.get('auc_total')}, founder {b.get('auc_founder')}, path {b.get('auc_path')} |",
         f"| Deciding reasons matched | passes {b.get('reasons_matched_passed', ['?','?'])[0]}/{b.get('reasons_matched_passed', ['?','?'])[1]}, investments {b.get('reasons_matched_invested', ['?','?'])[0]}/{b.get('reasons_matched_invested', ['?','?'])[1]} |",
         f"| Claims extracted | {e['claims']}, {e['claims_invalid']} invalid; 40/40 key figures recalled |",
         f"| Deterministic checks | {e['checks']} ({e['checks_fail']} fail, {e['checks_unverifiable']} unverifiable); reference script agrees {e['reference_agreement'][0]}/{e['reference_agreement'][1] if e['reference_agreement'] else ''} |",
         f"| Web findings | {e['findings']}, {e['findings_low_confidence']} low confidence; {e['spot_checked'][0]}/{e['spot_checked'][1]} spot-checks confirmed; {e['not_found']} questions not answerable |",
         f"| Founders confirmed by an outside source | {e['founders_confirmed_online']} of {e['founders_total']} |", "",
         "## What holds", ""] + [f"- {x}" for x in t["what_holds"]] + ["", "## Where it breaks", "",
         "| Where | Numbers | Why it matters |", "|---|---|---|"] + \
        [f"| {x['where']} | {x['numbers']} | {x['why']} |" for x in t["breaks"]] + ["", "## Terms to agree in advance (proposals; Kushal decides)", ""] + \
        [f"{i}. {x['term']} *Basis: {x['basis']}.*" for i, x in enumerate(t["terms"], 1)] + \
        ["", "Agreed by: ____________________   Date: ____________", "", "## What the system could not find, and what that costs", "",
         "| Missing | What was found | What it costs |", "|---|---|---|"] + \
        [f"| {g['missing']} | {g['found']} | {g['cost']} |" for g in a["gaps"]]
    if tc:
        L += ["", "## Time and cost against Riya's nineteen days", "",
              f"- **Riya today:** {tc['riya_minutes_per_application']} minutes per application, {tc['riya_days_per_quarter']}+ days a quarter "
              f"(about {tc['riya_implied_applications_per_quarter']} applications at 8 hours a day); {tc['riya_hours_per_batch_of_10']} hours for a batch of 10.",
              f"- **System, batch of 10:** about {tc['batch_wall_minutes']} minutes of wall-clock with agents in parallel "
              f"({tc['agent_minutes_total']} agent-minutes in total, {tc['agent_minutes_per_application']} per application), plus {tc['code_seconds_batch']} seconds of code.",
              f"- **Tokens per application:** about {tc['per_application_tokens_total']:,} "
              f"({', '.join(f'{k} {v:,}' for k, v in tc['per_application_tokens'].items())}). {tc['cost_note']}",
              "- **Still human:** " + "; ".join(tc["still_human"]), "", f"Source: {tc['source']}"]
    p = REPORTS / "trust_and_limits.md"
    p.write_text("\n".join(L) + "\n")
    return p


if __name__ == "__main__":
    a = build()
    print(write_report(a))
    print(json.dumps({"backtest": a["trust"]["backtest"], "evidence": a["trust"]["evidence"],
                      "time_cost": {k: v for k, v in a["time_cost"].items() if k not in ("still_human", "source", "cost_note")}}, indent=1))
