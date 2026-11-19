"""Out-of-sample harness: freeze before decisions, blind, decide (human only), evaluate once against the bar."""
import json
import sqlite3

import pytest

from aic import config, db, oos
from aic.oos import OOSError

BANDS = {"A": "call", "B": "call", "C": "pass", "D": "pass", "E": "hold",
         "F": "partner_review", "G": "pass", "H": "call", "I": "pass", "J": "pass"}


@pytest.fixture
def env(tmp_path):
    conn = db.connect(":memory:")
    for co, band in BANDS.items():
        (tmp_path / f"{co}.json").write_text(json.dumps(
            {"company": co, "band": band, "total": 60.0, "band_reasons": [f"score band: {band}"],
             "swing_criteria": [{"criterion": "T1"}, {"criterion": "F2"}]}))
    return conn, tmp_path


def freeze(env, cos=None, batch="b1"):
    conn, d = env
    return oos.freeze(conn, batch, "Swapnil", cos or list(BANDS), scores_dir=d)


def decide_all(conn, decisions, by="Kushal"):
    for co, dec in decisions.items():
        oos.decide(conn, co, dec, "one-line reason", by)


def test_freeze_needs_score_cards(env):
    with pytest.raises(OOSError, match="no score card"):
        oos.freeze(env[0], "b1", "Swapnil", ["Nope"], scores_dir=env[1])


def test_freeze_refuses_already_decided(env):
    oos.decide(env[0], "A", "call", "reason", "Kushal")
    with pytest.raises(OOSError, match="already decided"):
        freeze(env)


def test_company_in_one_batch_only_and_tables_append_only(env):
    freeze(env, ["A", "B"])
    with pytest.raises(OOSError, match="already in a frozen batch"):
        freeze(env, ["B", "C"], batch="b2")
    conn = env[0]
    for sql in ("UPDATE oos_members SET band='call'", "DELETE FROM oos_members", "UPDATE oos_batches SET frozen_by='x'",
                "DELETE FROM oos_batches"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)


def test_blinded_until_evaluated(env):
    freeze(env)
    assert oos.blinded_companies(env[0]) == set(BANDS)


@pytest.mark.parametrize("by", ["model", "Claude", "system", ""])
def test_decision_needs_named_human(env, by):
    with pytest.raises(sqlite3.IntegrityError):
        oos.decide(env[0], "A", "call", "reason", by)


def test_decision_validation(env):
    with pytest.raises(OOSError):
        oos.decide(env[0], "A", "maybe", "reason", "Kushal")
    with pytest.raises(OOSError):
        oos.decide(env[0], "A", "call", "two\nlines", "Kushal")


def test_evaluate_refuses_until_all_decided(env):
    freeze(env)
    decide_all(env[0], {"A": "call"})
    with pytest.raises(OOSError, match="not ready"):
        oos.evaluate(env[0], "b1", reports_dir=None)


def test_decision_before_freeze_is_invalid(env):
    freeze(env, ["A"])
    oos.decide(env[0], "A", "call", "reason", "Kushal", at="2000-01-01T00:00:00+05:30")
    st = oos.status(env[0], "b1")
    assert st["invalid"] and not st["decided"]
    with pytest.raises(OOSError, match="not ready"):
        oos.evaluate(env[0], "b1", reports_dir=None)


def agreeing():
    return {"A": "call", "B": "call", "C": "pass", "D": "pass", "E": "pass", "F": "pass",
            "G": "pass", "H": "call", "I": "pass", "J": "pass"}


def test_evaluate_meets_bar(env, tmp_path):
    freeze(env)
    decide_all(env[0], agreeing())
    r = oos.evaluate(env[0], "b1", reports_dir=tmp_path)
    # F is partner_review -> no commitment; E is hold vs pass -> agree. 9/10 agree, needed 8.
    assert (r["agree"], r["counted"], r["needed"], r["no_commitment"]) == (9, 10, 8, 1)
    assert r["meets_bar"] and r["calls_scored_pass"] == []
    assert (tmp_path / "oos_b1.md").exists()
    assert oos.blinded_companies(env[0]) == set()


def test_a_call_scored_pass_fails_the_bar_even_with_high_agreement(env):
    freeze(env)
    d = agreeing()
    d["C"] = "call"                       # partners call a company the screener scored pass
    decide_all(env[0], d)
    r = oos.evaluate(env[0], "b1", reports_dir=None)
    assert r["agree"] == 8 and r["calls_scored_pass"] == ["C"] and not r["meets_bar"]


def test_review_more_is_excluded_and_bar_scales(env):
    freeze(env)
    d = agreeing()
    d["A"] = d["B"] = "review_more"
    decide_all(env[0], d)
    r = oos.evaluate(env[0], "b1", reports_dir=None)
    assert r["excluded"] == 2 and r["counted"] == 8 and r["needed"] == 7   # ceil(0.8 * 8)


def test_evaluate_once_and_uses_frozen_snapshot(env):
    conn, d = env
    freeze(env)
    (d / "A.json").write_text(json.dumps({"company": "A", "band": "pass", "total": 1.0}))   # rescored later
    decide_all(conn, agreeing())
    r = oos.evaluate(conn, "b1", reports_dir=None)
    assert next(x for x in r["rows"] if x["company"] == "A")["model_band"] == "call"
    with pytest.raises(OOSError, match="already evaluated"):
        oos.evaluate(conn, "b1", reports_dir=None)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE oos_results SET result_json='{}'")


def test_bar_comes_from_config():
    bar = config.load()["oos_test"]
    assert bar["min_agree"] == 8 and bar["of"] == 10 and bar["call_scored_pass_allowed"] == 0


def test_dashboard_leaves_blinded_companies_out(monkeypatch):
    from aic import dashboard
    if not (dashboard.DATA / "scores" / "Pumpwise.json").exists():
        pytest.skip("no scores")
    monkeypatch.setattr(oos, "blinded_companies", lambda conn: {"Pumpwise"})
    d = dashboard.collect()
    assert "Pumpwise" not in [c["company"] for c in d["companies"]] and d["blinded"] == ["Pumpwise"]
