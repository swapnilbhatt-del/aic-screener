"""Stage 2 tests: the comparison engine (no seed needed) and every company check (seed-dependent)."""
import json
import math
from pathlib import Path

import pytest

from aic import checks
from aic.checks import Check, Input, compare, credential_tokens, _token_in

ROOT = Path(__file__).resolve().parent.parent


# ---- engine ---------------------------------------------------------------

def test_compare_equal_and_tolerance_boundary_inclusive():
    assert compare(100, 100, 0.05)["status"] == "PASS"
    assert compare(100, 105, 0.05)["status"] == "PASS"      # exactly 5%: inclusive
    assert compare(100, 105.01, 0.05)["status"] == "FAIL"
    assert compare(100, 95, 0.05)["status"] == "PASS"


def test_compare_direction_reports_ratio():
    r = compare(91200, 9120, 0.05)
    assert r["status"] == "FAIL" and "10.00x the recomputed" in r["direction"]
    r = compare(14400, 144000, 0.05)
    assert "10.00x lower" in r["direction"]


def test_compare_bounds():
    assert compare(4, 2.83, 0.05, "upper")["status"] == "PASS"     # '< 4 months'
    assert compare(2000, 2860, 0.05, "upper")["status"] == "FAIL"  # 'under INR 2,000'
    assert compare(2500, 3250, 0.05, "lower")["status"] == "PASS"
    assert compare(2500, 2400, 0.05, "lower")["status"] == "FAIL"


def test_compare_zero_stated():
    assert compare(0, 0, 0.05)["status"] == "PASS"
    assert compare(0, 1, 0.05)["status"] == "FAIL"


def test_credential_tokens_and_aliases():
    assert {"Goldman", "Sachs", "Google", "IIM", "Ahmedabad", "MBA"} <= credential_tokens("Ex-Goldman Sachs. Ex-Google. MBA, IIM Ahmedabad")
    assert "Qualified" not in credential_tokens("Qualified CA")
    assert _token_in("CA", "Qualified Chartered Accountant")
    assert "CA" in credential_tokens("Qualified Chartered Accountant")
    assert _token_in("4 year", "4 years in practice")
    assert not _token_in("10 week", "internship")
    assert not _token_in("Google", "a large technology company")


class FakeCtx:
    def __init__(self, claims):
        self.claims = claims


def make_runner(claims):
    r = checks.Runner.__new__(checks.Runner)
    r.ctx = checks.Ctx.__new__(checks.Ctx)
    r.ctx.company, r.ctx.claims = "X", claims
    r.company, r.tol, r.checks = "X", 0.05, []
    return r


def claim(id, metric, doc, aw, value, entity=None, components=None, qualifier=None):
    return {"id": id, "metric": metric, "doc": doc, "as_written": aw, "value": value, "valid": True,
            "quote": aw, "cite": f"X/{doc} p1", "entity": entity, "components": components, "qualifier": qualifier,
            "page": 1, "kind": "count"}


def test_market_formula_product_and_failure():
    r = make_runner([claim("m", "market_tam_inr", "deck", "INR 91,200 Cr", 9.12e11, components=[
        {"as_written": "38M", "value": 38e6, "kind": "count"}, {"as_written": "INR 2,400", "value": 2400, "kind": "inr"}])])
    r.market_formulas()
    c = r.checks[0]
    assert c.status == "FAIL" and c.recomputed == pytest.approx(9.12e10) and c.kind == "formula"


def test_missing_input_is_uncheckable_never_imputed():
    r = make_runner([claim("a", "cac_inr", "deck", "INR 340", 340)])
    r.formula("x", "needs ltv", "internal", lambda: r.ctx.get("cac", "cac_inr", "deck"),
              lambda: [r.ctx.get("ltv", "ltv_cac", "deck")], lambda v: v, "ltv")
    assert r.checks[0].status == "UNCHECKABLE" and r.checks[0].recomputed is None


def test_cross_document_headline_and_materiality():
    r = make_runner([claim("d", "customers_paying", "deck", "31 paying", 31),
                     claim("f", "customers_paying", "form", "24 paying", 24),
                     claim("d2", "team_size", "deck", "8", 8), claim("f2", "team_size", "form", "8", 8)])
    r.cross_documents()
    by = {c.id: c for c in r.checks}
    assert by["xdoc.customers_paying"].status == "FAIL"
    assert by["xdoc.customers_paying"].material_field == "traction"
    assert by["xdoc.team_size"].status == "PASS"


def test_cross_document_bound_in_form():
    r = make_runner([claim("d", "cac_inr", "deck", "INR 2,860", 2860),
                     claim("f", "cac_inr", "form", "under INR 2,000", 2000)])
    r.cross_documents()
    assert r.checks[0].status == "FAIL" and r.checks[0].bound == "upper"


def test_raise_missing_number_in_one_doc_fails():
    c = claim("d", "raise_inr", "deck", "We are raising funds", None)
    r = make_runner([c, claim("f", "raise_inr", "form", "INR 1.2 Cr", 1.2e7)])
    r.cross_documents()
    assert r.checks[0].status == "FAIL" and r.checks[0].material_field is None  # omission, not contradiction


# ---- every company check, against the seed --------------------------------

built = (ROOT / "data" / "claims" / "CAPilot.json").exists()
seed = pytest.mark.skipif(not built, reason="claims not built")

EXPECTED = {
    ("CAPilot", "arr_from_mrr"): "PASS", ("CAPilot", "chart_oct_vs_mrr"): "PASS",
    ("CAPilot", "deck_paying_eq_form_paying_plus_trial"): "PASS", ("CAPilot", "arpu_in_price_band_low"): "PASS",
    ("CAPilot", "xdoc.customers_paying"): "FAIL", ("CAPilot", "xdoc.credentials.dhruv_shah"): "PASS",
    ("CareCorner", "market.tam"): "PASS", ("CareCorner", "market.sam"): "PASS", ("CareCorner", "market.som"): "PASS",
    ("CareCorner", "clinic_runrate_vs_maturity"): "FAIL", ("CareCorner", "use_of_funds_clinics"): "PASS",
    ("CareCorner", "channel_mix_sum"): "PASS",
    ("EarnWise", "market.tam"): "FAIL", ("EarnWise", "chart_sum"): "PASS",
    ("EarnWise", "advance_per_worker_vs_tam"): "FAIL", ("EarnWise", "xdoc.customers_live"): "FAIL",
    ("EarnWise", "xdoc.team_size"): "FAIL", ("EarnWise", "xdoc.credentials.rohit_arora"): "FAIL",
    ("GrainKind", "market.tam"): "FAIL", ("GrainKind", "market.sam"): "FAIL", ("GrainKind", "market.som"): "PASS",
    ("GrainKind", "blended_cac_from_channels"): "PASS", ("GrainKind", "som_spend_vs_tam_spend"): "FAIL",
    ("GrainKind", "som_households"): "PASS", ("GrainKind", "sku_share_sum"): "PASS", ("GrainKind", "ltv_cac"): "UNCHECKABLE",
    ("Pumpwise", "market.tam"): "PASS", ("Pumpwise", "tam_at_observed_sensors"): "FAIL",
    ("Pumpwise", "mrr_from_sensors"): "PASS", ("Pumpwise", "hardware_revenue"): "PASS", ("Pumpwise", "avg_sensors"): "PASS",
    ("Pumpwise", "pilot_conversion"): "PASS", ("Pumpwise", "cac"): "PASS", ("Pumpwise", "first_year_gp"): "PASS",
    ("Pumpwise", "payback"): "PASS", ("Pumpwise", "annual_sub_eq_monthly"): "PASS", ("Pumpwise", "msme_base"): "PASS",
    ("RentRoute", "market.share"): "PASS", ("RentRoute", "chart_sum"): "PASS", ("RentRoute", "gross_fee"): "PASS",
    ("RentRoute", "net_fee"): "PASS", ("RentRoute", "deck_revenue_basis"): "FAIL",
    ("Settlr", "market.tam"): "FAIL", ("Settlr", "market.sam"): "FAIL", ("Settlr", "market.som"): "FAIL",
    ("Settlr", "volume_per_sme_vs_tam"): "FAIL", ("Settlr", "arpu"): "PASS", ("Settlr", "payback"): "FAIL",
    ("StockSathi", "market.tam"): "PASS", ("StockSathi", "cac"): "PASS", ("StockSathi", "payback"): "PASS",
    ("StockSathi", "channel_sum"): "PASS", ("StockSathi", "credit_funding"): "FAIL",
    ("StockSathi", "xdoc.customers_onboarded"): "FAIL", ("StockSathi", "xdoc.cac_inr"): "FAIL",
    ("Talkbook", "market.tam"): "PASS", ("Talkbook", "mrr_seats_deck"): "FAIL", ("Talkbook", "mrr_seats_form"): "FAIL",
    ("Talkbook", "arpu_from_seats"): "FAIL", ("Talkbook", "arpu_from_mrr"): "PASS", ("Talkbook", "payback"): "FAIL",
    ("Talkbook", "xdoc.mrr_inr"): "FAIL", ("Talkbook", "channel_sum"): "PASS",
    ("Yatrika", "revenue_commission"): "PASS", ("Yatrika", "travellers"): "FAIL", ("Yatrika", "xdoc.raise_inr"): "FAIL",
}


@pytest.fixture(scope="module")
def results():
    return {(c.company, c.id): c for co in checks.COMPANIES for c in checks.run(co)}


@seed
@pytest.mark.parametrize("key,status", sorted(EXPECTED.items()))
def test_company_check(results, key, status):
    assert key in results, f"check {key} not produced"
    assert results[key].status == status, (key, results[key].status, results[key].note)


@seed
def test_every_check_has_cited_inputs(results):
    for c in results.values():
        if c.status == "UNCHECKABLE":
            assert c.note
            continue
        for i in c.inputs + ([c.stated] if c.stated else []):
            assert i.cite, (c.company, c.id, i.label)


@seed
def test_talkbook_payback_is_within_stated_precision(results):
    c = results[("Talkbook", "payback")]
    assert c.status == "FAIL" and c.within_stated_precision is True


@seed
def test_reference_script_fully_reconciled():
    from aic import reference_reconcile
    checks.main()
    rows, extra, _ = reference_reconcile.reconcile()
    assert len(rows) == 34 and all(r["agree"] for r in rows)


@seed
def test_credit_structure_is_material_per_config(results):
    from aic import config
    assert "credit_structure" in config.load()["integrity_cap"]["material_fields"]
    assert results[("StockSathi", "credit_funding")].material_field == "credit_structure"
