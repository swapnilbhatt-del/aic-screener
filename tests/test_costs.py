"""AI cost & ROI page: same units, placeholders labelled, nothing imputed before metering."""
import copy

from aic import config, costs, db, llm
from tests.test_llm import FakeClient


def test_riya_cost_in_rupees_from_config():
    cfg = copy.deepcopy(config.load())
    r = costs.build(db.connect(":memory:"), cfg)["roi"]
    assert r["riya_per_application_inr"] == 500            # 30 min at the ₹1,000/h placeholder
    assert r["riya_per_quarter_inr"] == 19 * 8 * 1000 and r["riya_rate_is_placeholder"] is True


def test_unmetered_system_cost_is_not_imputed():
    r = costs.build(db.connect(":memory:"))
    assert r["metered"]["per_application_inr"] is None and r["roi"]["measured"] is False
    assert "saving_per_quarter_inr" not in r["roi"] and "not ROI" not in r["roi"]["caveat"]


def test_metered_calls_feed_the_roi():
    conn, cfg = db.connect(":memory:"), copy.deepcopy(config.load())
    for co in ("A", "B"):
        llm.call(conn, "scoring", [{"role": "user", "content": co}], company=co, client=FakeClient(), cfg=cfg, max_tokens=100)
    r = costs.build(conn, cfg)
    per_app = (10_000 * 4 + 1_000 * 20) / 1e6 * cfg["ai"]["usd_inr"]
    assert r["metered"]["applications"] == 2 and abs(r["roi"]["system_per_application_inr"] - per_app) < 0.01
    assert r["roi"]["system_share_pct"] == round(100 * r["metered"]["per_application_inr"] / 500, 1)
