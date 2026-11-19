"""Recall check: key figures that Stage 2 depends on must be present, correctly tagged, with code-computed
values. Expected values were read from the source PDFs by the main session (independent of the extractors)."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
C = ROOT / "data" / "claims"
pytestmark = pytest.mark.skipif(not (C / "CAPilot.json").exists(), reason="claims not built")

# (company, doc, metric, expected value)
EXPECTED = [
    ("CAPilot", "deck", "customers_paying", 31), ("CAPilot", "form", "customers_paying", 24),
    ("CAPilot", "form", "customers_trial", 7), ("CAPilot", "form", "mrr_inr", 78000),
    ("CAPilot", "deck", "arr_inr", 9.4e5), ("CAPilot", "form", "raise_inr", 1.5e7),
    ("CareCorner", "deck", "market_tam_inr", 1.14e12), ("CareCorner", "deck", "market_som_inr", 3.5e8),
    ("CareCorner", "deck", "capex_inr", 2.8e6), ("CareCorner", "form", "revenue_month_inr", 9.8e5),
    ("EarnWise", "deck", "market_tam_inr", 1.44e11), ("EarnWise", "deck", "team_size", 12),
    ("EarnWise", "form", "team_size", 5), ("EarnWise", "deck", "customers_live", 3), ("EarnWise", "form", "customers_live", 1),
    ("GrainKind", "deck", "market_tam_inr", 9.12e11), ("GrainKind", "deck", "market_sam_inr", 1.44e11),
    ("GrainKind", "deck", "cac_inr", 340), ("GrainKind", "form", "gross_margin_pct", 0.48),
    ("Pumpwise", "deck", "market_tam_inr", 1.62e11), ("Pumpwise", "deck", "cac_inr", 73000),
    ("Pumpwise", "form", "customers_paying", 6), ("Pumpwise", "deck", "mrr_inr", 1.05e5),
    ("RentRoute", "form", "revenue_net_inr", 5.5e5), ("RentRoute", "deck", "revenue_gross_inr", 11e5),
    ("RentRoute", "form", "volume_cumulative_inr", 6.1e7),
    ("Settlr", "deck", "market_tam_inr", 9.4e12), ("Settlr", "deck", "cac_inr", 14500),
    ("Settlr", "deck", "payback_months", 7), ("Settlr", "form", "raise_inr", 3e8),
    ("StockSathi", "deck", "customers_onboarded", 38), ("StockSathi", "form", "customers_onboarded", 42),
    ("StockSathi", "deck", "cac_inr", 2860), ("StockSathi", "deck", "market_som_inr", 5.18e9),
    ("Talkbook", "deck", "mrr_inr", 2.1e5), ("Talkbook", "form", "mrr_inr", 1.9e5),
    ("Talkbook", "deck", "seats_paid", 340), ("Talkbook", "deck", "arpu_month_inr", 13000),
    ("Yatrika", "form", "revenue_cumulative_inr", 4.6e5), ("Yatrika", "form", "raise_inr", 1.2e7),
]


def claims(co):
    return json.loads((C / f"{co}.json").read_text())["claims"]


@pytest.mark.parametrize("co,doc,metric,value", EXPECTED)
def test_key_claim_present(co, doc, metric, value):
    hits = [c for c in claims(co) if c["doc"] == doc and c["metric"] == metric and c["valid"]]
    assert hits, f"{co} {doc} {metric}: no claim"
    assert any(c["value"] is not None and abs(c["value"] - value) <= 1e-6 * max(1, value) for c in hits), \
        f"{co} {doc} {metric}: values {[c['value'] for c in hits]} != {value}"


@pytest.mark.parametrize("co", ["CareCorner", "EarnWise", "GrainKind", "Pumpwise", "Settlr", "StockSathi", "Talkbook"])
def test_market_formulas_have_components(co):
    m = [c for c in claims(co) if c["metric"] in ("market_tam_inr", "market_sam_inr", "market_som_inr")]
    assert m and all(len(c.get("components") or []) >= 2 for c in m), co
    assert all(comp["value"] is not None for c in m for comp in c["components"])
