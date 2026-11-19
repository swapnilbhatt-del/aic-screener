"""Stage 1 entry point: python -m aic.ingest

Builds per-page text, parses forms deterministically, finalises model-extracted claims (validated in code),
and assembles one structured record per application. Also builds memo (blind + sealed) and notes records.
"""
import json
from pathlib import Path

from . import claims, forms, memos, notes, text

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "data" / "applications"

COMPANIES = ["CAPilot", "CareCorner", "EarnWise", "GrainKind", "Pumpwise",
             "RentRoute", "Settlr", "StockSathi", "Talkbook", "Yatrika"]

GROUPS = {
    "company": {"company_name", "location", "incorporated", "sector", "stage", "team_size", "time_commitment"},
    "founders": {"founder_name", "founder_role", "founder_credential", "founder_prior_startup", "cofounder_departure"},
    "traction": {"customers_paying", "customers_trial", "customers_pilot", "customers_onboarded", "customers_repeat",
                 "customers_churned", "customers_live", "customers_in_cohort", "users_registered", "users_paying", "seats_paid", "units_live",
                 "transactions_count", "pilot_to_paid_pct", "revenue_month_inr", "revenue_cumulative_inr",
                 "revenue_gross_inr", "revenue_net_inr", "mrr_inr", "arr_inr", "gmv_month_inr", "gmv_period_inr",
                 "volume_month_inr", "volume_cumulative_inr", "time_series"},
    "unit_economics": {"cac_inr", "cac_channel_inr", "channel_mix_pct", "payback_months", "gross_margin_pct",
                       "contribution_margin_pct", "ltv_cac", "repeat_rate_pct", "nrr_pct", "arpu_month_inr",
                       "price_inr", "take_rate_pct", "partner_cost_pct", "margin_per_unit_month_inr", "capex_inr", "breakeven", "order_value_inr"},
    "market": {"market_tam_inr", "market_sam_inr", "market_som_inr", "market_headline_inr", "market_share_claim"},
    "funding": {"raise_inr", "valuation_post_inr", "existing_investment_inr", "use_of_funds_pct", "milestone_target",
                "other_investors", "source_of_application"},
    "risk_competition": {"competitor_named", "competition_claim", "regulatory_dependency", "credit_funding",
                         "credit_book_inr", "defaults", "key_risk", "dependency", "evidence_of_value"},
}


def group_of(metric: str) -> str:
    for g, ms in GROUPS.items():
        if metric in ms:
            return g
    return "other"


def build_application(company: str) -> dict:
    form_doc = text.load(f"{company}/form")
    deck_doc = text.load(f"{company}/deck")
    form = forms.parse_form(form_doc)
    for k, v in form.items():
        v["cite"] = text.cite(form_doc, v["page"])
    founders = [dict(forms.parse_founder(form[k]["value"]), cite=form[k]["cite"])
                for k in ("founder_1", "founder_2") if k in form]
    rec = {"company": company,
           "sources": {"deck": deck_doc["source"], "form": form_doc["source"],
                       "deck_pages": deck_doc["n_pages"], "form_pages": form_doc["n_pages"]},
           "form_fields": form, "form_founders": founders, "claims": {}, "claims_status": "missing"}
    if (claims.CLAIMS_DIR / f"{company}.raw.json").exists():
        c = claims.finalise(company)
        for cl in c["claims"]:
            rec["claims"].setdefault(group_of(cl["metric"]), []).append(cl)
        rec["claims_status"] = f"{c['n_claims']} claims, {c['n_invalid']} invalid"
        rec["n_claims"], rec["n_invalid"] = c["n_claims"], c["n_invalid"]
    APPS.mkdir(parents=True, exist_ok=True)
    (APPS / f"{company}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    return rec


def main() -> dict:
    docs = text.build_all()
    summary = {"documents": len(docs), "pages": sum(d["n_pages"] for d in docs), "applications": {}}
    for co in COMPANIES:
        r = build_application(co)
        summary["applications"][co] = {
            "form_fields": len(r["form_fields"]), "claims": r.get("n_claims", 0), "invalid": r.get("n_invalid", 0),
            "by_group": {g: len(v) for g, v in sorted(r["claims"].items())},
            "by_doc": {d: sum(1 for v in r["claims"].values() for c in v if c.get("doc") == d) for d in ("deck", "form")}}
    summary["memos"] = memos.build()
    summary["notes"] = notes.build()
    (ROOT / "data" / "stage1_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
