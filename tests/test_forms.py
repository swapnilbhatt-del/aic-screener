"""Form parser tests. Seed-dependent tests skip when seed/ is absent (it is gitignored)."""
import pytest

from aic import forms, text

COMPANIES = ["CAPilot", "CareCorner", "EarnWise", "GrainKind", "Pumpwise",
             "RentRoute", "Settlr", "StockSathi", "Talkbook", "Yatrika"]
CORE = ["company_name", "sector_selected", "stage_selected", "team_size", "founder_1",
        "time_commitment", "raise", "valuation", "source", "anything_else"]

need_seed = pytest.mark.skipif(not (text.TEXT_DIR / "CAPilot__form.json").exists(),
                               reason="seed text not built (run python -m aic.ingest)")


def fake_doc(layout_pages, plain_pages=None):
    plain_pages = plain_pages or layout_pages
    return {"doc_id": "X/form", "pages": [{"page": i + 1, "layout": l, "plain": p}
                                          for i, (l, p) in enumerate(zip(layout_pages, plain_pages))]}


def test_row_continuation_and_wrapped_label():
    layout = ("Company\n"
              " Company name        Acme (Acme Pvt. Ltd.)\n"
              " What have you built?  A thing that does\n"
              "                       many things.\n"
              " Other investors in  None yet.\n"
              " conversation\n")
    f = forms.parse_form(fake_doc([layout]))
    assert f["company_name"]["value"] == "Acme (Acme Pvt. Ltd.)"
    assert f["product"]["value"] == "A thing that does many things."
    assert f["other_investors"]["value"] == "None yet."


def test_ligature_gaps_are_respaced_from_plain_text():
    layout = " Customers        24 paying CA ﬁrms, 7 on fr        ee trial.\n"
    plain = "Customers 24 paying CA ﬁrms, 7 on free trial."
    f = forms.parse_form(fake_doc([layout], [plain]))
    assert f["Customers"]["value"] == "24 paying CA firms, 7 on free trial."
    assert f["Customers"]["respaced"] is True


def test_free_text_section():
    layout = " Amount raising    INR 1 Cr\nAnything else we should know?\nWe would welcome a call.\n"
    f = forms.parse_form(fake_doc([layout]))
    assert f["raise"]["value"] == "INR 1 Cr"
    assert f["anything_else"]["value"] == "We would welcome a call."


def test_parse_founder_variants():
    a = forms.parse_founder("Dhruv Shah, CEO. Qualified Chartered Accountant. linkedin.com/in/dhruv-shah-example")
    assert (a["name"], a["role"]) == ("Dhruv Shah", "CEO")
    assert a["linkedin"] == "linkedin.com/in/dhruv-shah-example"
    b = forms.parse_founder("Aarav Deshmukh, CEO LinkedIn: linkedin.com/in/x Background: FMCG, 8 years.")
    assert (b["name"], b["role"], b["background"]) == ("Aarav Deshmukh", "CEO", "FMCG, 8 years.")
    c = forms.parse_founder("Manish Joshi. 10 years running his family's travel agency.")
    assert c["name"] == "Manish Joshi" and c["role"] is None


@need_seed
@pytest.mark.parametrize("company", COMPANIES)
def test_every_form_has_core_fields_with_pages(company):
    f = forms.parse_form(text.load(f"{company}/form"))
    for k in CORE:
        assert k in f, f"{company} missing {k}"
        assert f[k]["page"] >= 1 and f[k]["value"]
    assert all(v["respaced"] for v in f.values())


@need_seed
def test_known_values():
    f = forms.parse_form(text.load("CAPilot/form"))
    assert f["Customers"]["value"] == "24 paying CA firms, 7 on free trial. 2 firms have churned."
    s = forms.parse_form(text.load("StockSathi/form"))
    assert s["How is credit funded?"]["value"].startswith("Credit is provided through our NBFC partner")
    assert s["anything_else"]["page"] == 3
