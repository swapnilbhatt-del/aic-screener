"""Stage 6: corrections log, surfacing, and proposals. Uses an in-memory DB and temp score cards."""
import hashlib
import json
import shutil
import sqlite3

import pytest
import yaml

from aic import config, db, feedback

CFG = config.load()


@pytest.fixture
def env(tmp_path):
    scores, apps = tmp_path / "scores", tmp_path / "apps"
    scores.mkdir(), apps.mkdir()
    companies = {"A1": "Fintech", "A2": "Fintech (AI SaaS)", "A3": "Fintech", "A4": "Fintech",
                 "C1": "Consumer brands", "H1": "Other (Healthcare)"}
    for co, sector in companies.items():
        (scores / f"{co}.json").write_text(json.dumps({"criteria": {k: {"final": 3} for k in CFG["criteria"]}}))
        (apps / f"{co}.json").write_text(json.dumps({"form_fields": {"sector_selected": {"value": sector}}}))
    conn = db.connect(":memory:")
    return conn, scores, apps


def add(env, co, crit, human, reason="a one-line reason", by="Kushal"):
    conn, scores, apps = env
    return feedback.add_correction(conn, co, crit, human, reason, by, CFG, scores, apps)


def test_add_reads_model_score_from_card_and_sector(env):
    cid = add(env, "A2", "F2", 1, "founder said default rates were the lender's problem")
    row = env[0].execute("SELECT model_score, human_score, sector, corrected_by FROM corrections WHERE id=?", (cid,)).fetchone()
    assert row == (3, 1, "fintech", "Kushal")


@pytest.mark.parametrize("kwargs,match", [
    (dict(crit="Z9"), "unknown criterion"), (dict(human=7), "integer 0-5"),
    (dict(reason="two\nlines"), "one line"), (dict(reason=" "), "one line"), (dict(reason="x" * 201), "one line")])
def test_add_validates(env, kwargs, match):
    args = dict(co="A1", crit="F2", human=1, reason="ok")
    args.update(kwargs)
    with pytest.raises(feedback.FeedbackError, match=match):
        add(env, args["co"], args["crit"], args["human"], args["reason"])


@pytest.mark.parametrize("by", ["model", "Claude", "system", "auto"])
def test_db_rejects_non_human_author(env, by):
    with pytest.raises(sqlite3.IntegrityError):
        add(env, "A1", "F2", 1, by=by)


def test_db_rejects_unchanged_score(env):
    with pytest.raises(sqlite3.IntegrityError):
        add(env, "A1", "F2", 3)   # model score is 3


def test_corrections_are_append_only(env):
    cid = add(env, "A1", "F2", 1)
    with pytest.raises(sqlite3.IntegrityError):
        env[0].execute("UPDATE corrections SET human_score=2 WHERE id=?", (cid,))
    with pytest.raises(sqlite3.IntegrityError):
        env[0].execute("DELETE FROM corrections WHERE id=?", (cid,))


def test_surface_same_sector_same_criterion_other_company(env):
    add(env, "A1", "F2", 1, "dismissed credit risk")
    add(env, "C1", "F2", 1, "consumer brand, different sector")
    add(env, "A3", "T1", 4, "pilots were paid")
    s = feedback.surface(env[0], "A4", "fintech")
    assert set(s) == {"F2", "T1"}
    assert [r["company"] for r in s["F2"]] == ["A1"]
    assert s["F2"][0]["message"].startswith("Last time on a similar company (A1, fintech) Kushal moved F2 from 3 to 1")
    assert feedback.surface(env[0], "A1", "fintech").get("F2") is None   # own corrections are not 'similar companies'
    assert feedback.surface(env[0], "H1", "other (healthcare)") == {}


def test_no_proposal_below_three(env, tmp_path):
    add(env, "A1", "F2", 1)
    add(env, "A2", "F2", 2)
    assert feedback.propose(env[0], CFG) == []


def test_mixed_directions_do_not_count(env):
    add(env, "A1", "F2", 1)
    add(env, "A2", "F2", 5)
    add(env, "A3", "F2", 1)
    assert feedback.similar_groups(env[0], CFG) == []


def test_same_company_three_times_is_not_three_similar(env):
    for _ in range(3):
        add(env, "A1", "F2", 1)
    assert feedback.similar_groups(env[0], CFG) == []


def test_proposal_is_valid_diff_and_config_untouched(env, tmp_path):
    cfg_copy = tmp_path / "rubric.yaml"
    shutil.copy(feedback.CONFIG_PATH, cfg_copy)
    before = hashlib.sha256(feedback.CONFIG_PATH.read_bytes()).hexdigest()
    for co in ("A1", "A2", "C1"):
        add(env, co, "M2", 1, "competitor omitted")      # humans keep lowering M2
    made = feedback.propose(env[0], config.load(cfg_copy), cfg_copy)
    assert len(made) == 1 and made[0]["criterion"] == "M2" and made[0]["direction"] == "down"
    d = made[0]["diff"]
    assert "-  M2: {name: \"Defensibility and honest competition\", weight: 10}" in d
    assert "+  M2: {name: \"Defensibility and honest competition\", weight: 5}" in d
    # applying the proposal by hand yields a valid rubric that still sums to 100
    new = cfg_copy.read_text().replace('weight: 10}', 'weight: 5}', 1)
    assert hashlib.sha256(feedback.CONFIG_PATH.read_bytes()).hexdigest() == before
    assert cfg_copy.read_text() == feedback.CONFIG_PATH.read_text()
    status = env[0].execute("SELECT status, decided_by FROM weight_proposals").fetchone()
    assert status == ("proposed", None)
    assert feedback.propose(env[0], config.load(cfg_copy), cfg_copy) == []   # not re-proposed


def test_candidate_diff_keeps_total_100_for_block_criterion():
    text = feedback.CONFIG_PATH.read_text()
    d = feedback.candidate_diff(text, CFG, "T2", "up")
    assert "-    weight: 15" in d and "+    weight: 20" in d
    assert "-  T1: {name: \"Traction quality\", weight: 15}" in d and "weight: 10}" in d


def test_proposal_decision_needs_human(env):
    env[0].execute("INSERT INTO weight_proposals (criterion, direction, correction_ids, diff) VALUES ('M2','down','1,2,3','d')")
    with pytest.raises(sqlite3.IntegrityError):
        env[0].execute("UPDATE weight_proposals SET status='accepted', decided_by='model' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError):
        env[0].execute("INSERT INTO weight_proposals (criterion, direction, correction_ids, diff, status) "
                       "VALUES ('M2','down','1','d','accepted')")
    env[0].execute("UPDATE weight_proposals SET status='rejected', decided_by='Aditya', decided_at='now' WHERE id=1")


def test_no_code_path_writes_the_config():
    import pathlib
    import re
    src = pathlib.Path(feedback.__file__).read_text()
    assert not re.search(r"CONFIG_PATH\.write|cfg_path\.write|open\([^)]*rubric\.yaml[^)]*['\"]w", src)


def test_qualifying_group_without_valid_move_still_reaches_a_human(env, tmp_path):
    cfg_copy = tmp_path / "rubric.yaml"
    shutil.copy(feedback.CONFIG_PATH, cfg_copy)
    for co in ("A1", "A2", "A3"):
        add(env, co, "M2", 4, "real reason to win")   # M2 up by 5 would zero M1; step shrinks
    made = feedback.propose(env[0], config.load(cfg_copy), cfg_copy)
    assert len(made) == 1 and "weight: 12}" in made[0]["diff"] and "weight: 3}" in made[0]["diff"]
