"""Claim records extracted from decks and forms, and the code that verifies them.

A model proposes claims (metric, as_written, quote, doc, page). Code then:
  * checks the quote occurs on the cited page (whitespace/case-insensitive),
  * checks as_written occurs inside the quote,
  * computes the numeric value from as_written (the model never supplies numbers).
Claims that fail any check are kept but marked invalid, with the reason.
"""
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from . import text, units

ROOT = Path(__file__).resolve().parent.parent
CLAIMS_DIR = ROOT / "data" / "claims"

KINDS = {"inr", "count", "pct", "months", "ratio", "text"}

METRICS = {
    # company facts
    "company_name", "location", "incorporated", "sector", "stage", "team_size", "time_commitment",
    # founders
    "founder_name", "founder_role", "founder_credential", "founder_prior_startup", "cofounder_departure",
    # traction
    "customers_paying", "customers_trial", "customers_pilot", "customers_onboarded", "customers_repeat",
    "customers_churned", "customers_live", "customers_in_cohort", "users_registered", "users_paying", "seats_paid", "units_live",
    "transactions_count", "pilot_to_paid_pct",
    "revenue_month_inr", "revenue_cumulative_inr", "revenue_gross_inr", "revenue_net_inr", "mrr_inr", "arr_inr",
    "gmv_month_inr", "gmv_period_inr", "volume_month_inr", "volume_cumulative_inr", "time_series",
    # unit economics
    "cac_inr", "cac_channel_inr", "channel_mix_pct", "payback_months", "gross_margin_pct",
    "contribution_margin_pct", "ltv_cac", "repeat_rate_pct", "nrr_pct", "arpu_month_inr", "price_inr",
    "take_rate_pct", "partner_cost_pct", "margin_per_unit_month_inr", "capex_inr", "breakeven", "order_value_inr",
    # market
    "market_tam_inr", "market_sam_inr", "market_som_inr", "market_headline_inr", "market_share_claim",
    # funding
    "raise_inr", "valuation_post_inr", "existing_investment_inr", "use_of_funds_pct", "milestone_target",
    "other_investors", "source_of_application",
    # risk, competition, structure
    "competitor_named", "competition_claim", "regulatory_dependency", "credit_funding", "credit_book_inr",
    "defaults", "key_risk", "dependency", "evidence_of_value", "product_claim", "other",
}


def _float(s: str) -> Optional[float]:
    m = re.search(r"(\d+(?:,\d{2,3})*(?:\.\d+)?)", s)
    return float(m.group(1).replace(",", "")) if m else None


def compute_value(kind: str, as_written: str) -> Optional[float]:
    if kind == "inr":
        return units.parse_inr(as_written)
    if kind == "count":
        return units.parse_count(as_written)
    if kind == "pct":
        return units.parse_percent(as_written)
    if kind in ("months", "ratio"):
        return _float(as_written)
    return None


def series_scale(label: str) -> float:
    """Chart axis unit -> multiplier. 'Monthly revenue (INR lakh)' -> 1e5. Counts -> 1."""
    l = label.lower()
    if "inr" not in l and "₹" not in l:
        return 1.0
    if "lakh cr" in l:
        return units.LAKH_CRORE
    if re.search(r"\bcr(ore)?\b", l):
        return units.CRORE
    if "lakh" in l:
        return units.LAKH
    if "thousand" in l:
        return 1e3
    return 1.0


def validate_claim(c: dict, docs: dict) -> List[str]:
    errs = []
    for k in ("id", "metric", "kind", "as_written", "doc", "page", "quote"):
        if k not in c or c[k] in (None, ""):
            errs.append(f"missing {k}")
    if errs:
        return errs
    if c["metric"] not in METRICS:
        errs.append(f"unknown metric {c['metric']}")
    if c["kind"] not in KINDS:
        errs.append(f"unknown kind {c['kind']}")
    doc = docs.get(c["doc"])
    if doc is None:
        return errs + [f"unknown doc {c['doc']}"]
    if not (1 <= int(c["page"]) <= doc["n_pages"]):
        return errs + [f"page {c['page']} out of range"]
    found = text.find_quote(doc, c["quote"])
    if int(c["page"]) not in found:
        errs.append(f"quote not on cited page (found on {found or 'no page'})")
    if text.squash(c["as_written"]) not in text.squash(c["quote"]):
        errs.append("as_written not inside quote")
    if c["kind"] in ("inr", "count", "pct", "months", "ratio") and compute_value(c["kind"], c["as_written"]) is None:
        errs.append("could not compute a number from as_written")
    for i, comp in enumerate(c.get("components") or []):
        if text.squash(comp.get("as_written", "")) not in text.squash(c["quote"]):
            errs.append(f"component {i} as_written not inside quote")
        if compute_value(comp.get("kind", ""), comp.get("as_written", "")) is None:
            errs.append(f"component {i}: could not compute a number")
    return errs


def finalise(company: str) -> dict:
    """Validate raw claims, compute values in code, write <Company>.json. Raw stays as <Company>.raw.json."""
    raw = json.loads((CLAIMS_DIR / f"{company}.raw.json").read_text())
    docs = {"deck": text.load(f"{company}/deck"), "form": text.load(f"{company}/form")}
    out, ids = [], set()
    for c in raw["claims"]:
        errs = validate_claim(c, docs)
        if c.get("id") in ids:
            errs.append("duplicate id")
        ids.add(c.get("id"))
        c = dict(c)
        c["value"] = compute_value(c.get("kind", ""), c.get("as_written", ""))
        if c.get("metric") == "time_series" and c["value"] is not None:
            c["value"] *= series_scale(c.get("label", ""))
        for comp in c.get("components") or []:
            comp["value"] = compute_value(comp.get("kind", ""), comp.get("as_written", ""))
        if not errs and c["doc"] in docs:
            c["cite"] = text.cite(docs[c["doc"]], int(c["page"]))
        c["valid"] = not errs
        c["errors"] = errs
        out.append(c)
    rec = {"company": company, "extracted_by": raw.get("extracted_by"), "claims": out,
           "n_claims": len(out), "n_invalid": sum(not c["valid"] for c in out)}
    (CLAIMS_DIR / f"{company}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


if __name__ == "__main__":
    # python -m aic.claims validate <Company>
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        r = finalise(sys.argv[2])
        print(f"{r['company']}: {r['n_claims']} claims, {r['n_invalid']} invalid")
        for c in r["claims"]:
            if not c["valid"]:
                print(f"  {c.get('id')}: {'; '.join(c['errors'])}")
    else:
        print("usage: python -m aic.claims validate <Company>")
