"""Trust, gaps and time/cost pages: numbers come from the pipeline's files and agree with them."""
import json
from pathlib import Path

import pytest

from aic import assurance, dashboard

ROOT = Path(__file__).resolve().parent.parent
built = (ROOT / "data" / "backtest" / "result.json").exists()


@pytest.mark.skipif(not built, reason="pipeline data not built")
def test_trust_numbers_match_backtest_and_checks():
    a = assurance.build()
    t = a["trust"]
    bt = json.loads((ROOT / "data" / "backtest" / "result.json").read_text())
    assert t["backtest"]["agree"] == bt["agreement"]["as_scored"]["agree"]
    assert t["backtest"]["memos"] == len(bt["rows"])
    checks = [c for co in assurance.COMPANIES for c in json.loads((ROOT / "data" / "checks" / f"{co}.json").read_text())]
    assert t["evidence"]["checks"] == len(checks)
    assert t["evidence"]["reference_agreement"] == [34, 34]
    assert len(t["breaks"]) >= 5 and len(t["terms"]) >= 4 and t["what_holds"]


def test_gaps_cover_everything_the_case_says_is_not_given():
    names = " ".join(g["missing"].lower() for g in assurance.gaps())
    for item in ("thesis", "criteria", "anti-thesis", "portfolio", "beyond their own deck"):
        assert item in names, item
    assert all(g["cost"] for g in assurance.gaps())


def test_time_cost_adds_up():
    tc = assurance.time_cost()
    if not tc:
        pytest.skip("no run metrics")
    assert tc["per_application_tokens_total"] == sum(tc["per_application_tokens"].values())
    assert tc["riya_implied_applications_per_quarter"] == 304
    assert "No price is assumed" in tc["cost_note"]


@pytest.mark.skipif(not built, reason="pipeline data not built")
def test_site_build_ships_linked_files_with_relative_links():
    out = dashboard.build("site")
    html = out.read_text()
    assert "../seed/" not in html and "seed/applications/" in html
    for rel in dashboard.companion_files():
        assert (dashboard.SITE / rel).exists(), rel
    assert html.count("</script") == 2


@pytest.mark.skipif(not built, reason="pipeline data not built")
def test_artifact_build_is_full_content():
    html = dashboard.render(dashboard.collect(), publish=True, strip=False, base="")
    data = html[html.index('id="data">') + 10: html.index("</script>", html.index('id="data">'))]
    d = json.loads(data)
    assert d["backtest"] and d["assurance"]["trust"]["backtest"]
    assert "<!doctype" not in html and "../seed/" not in html
