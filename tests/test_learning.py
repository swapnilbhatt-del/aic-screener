"""Feedback loop (lecture 24 Nov): scope, bad-day flags, email edits, disagreement score, lessons in the prompt,
fine-tuning readiness and dataset export."""
import copy
import json
import sqlite3

import pytest

from aic import config, db, feedback, learning, outreach, runner

needs_data = pytest.mark.skipif(not (feedback.SCORES / "CAPilot.json").exists(), reason="no seed data")
FINTECH = ("RentRoute", "Settlr")          # same sector as CAPilot


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def correct(conn, co, crit="T1", delta=1, scope="general", by="Riya", reason="traction is paid pilots, not LOIs"):
    ms = feedback.model_score(co, crit)
    hs = ms + delta if 0 <= ms + delta <= 5 else ms - delta
    return feedback.add_correction(conn, co, crit, hs, reason, by, scope=scope)


def draft(conn, co="CAPilot", body="Hi Asha,\nWe'd like to talk.\nRiya"):
    return conn.execute("INSERT INTO outbox (company, to_addr, subject, body) VALUES (?, 'riya@placeholder.test', "
                        "'All In Capital', ?)", (co, body)).lastrowid


# ---- lessons ---------------------------------------------------------------------------------------
@needs_data
def test_lesson_needs_two_agreeing_companies_in_the_sector(conn):
    correct(conn, FINTECH[0])
    assert feedback.lessons(conn, "CAPilot") == []                       # one company is not enough
    correct(conn, FINTECH[1])
    les = feedback.lessons(conn, "CAPilot")
    assert len(les) == 1 and les[0]["companies"] == sorted(FINTECH) and len(les[0]["reasons"]) == 2
    assert feedback.lessons(conn, "Pumpwise") == []                      # other sector: nothing


@needs_data
def test_this_case_and_flagged_feedback_is_never_reused(conn):
    correct(conn, FINTECH[0], scope="this_case")
    cid = correct(conn, FINTECH[1])
    assert feedback.lessons(conn, "CAPilot") == []                       # one of the two is an exception
    correct(conn, FINTECH[0])
    assert feedback.lessons(conn, "CAPilot")
    feedback.flag(conn, "correction", cid, "bad_day", "rushed review on a Friday", "Kushal")
    assert feedback.lessons(conn, "CAPilot") == []                       # a bad-day edit drops out


def test_flags_need_a_named_human_and_are_append_only(conn):
    conn.execute("INSERT INTO corrections (company, criterion, model_score, human_score, reason, corrected_by) "
                 "VALUES ('A', 'T1', 1, 2, 'x', 'Riya')")
    for by in ("model", "claude", " "):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO feedback_flags (target, target_id, kind, reason, flagged_by) VALUES ('correction', 1, 'bad_day', 'x', ?)", (by,))
    feedback.flag(conn, "correction", 1, "bad_day", "x", "Kushal")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM feedback_flags")
    with pytest.raises(feedback.FeedbackError):
        feedback.flag(conn, "correction", 99, "bad_day", "x", "Kushal")


@needs_data
def test_scoring_prompt_carries_agreed_lessons_only(conn):
    assert "past_feedback" not in json.loads(runner.build_request("scoring", "CAPilot", conn=conn)["messages"][0]["content"])
    for co in FINTECH:
        correct(conn, co)
    req = runner.build_request("scoring", "CAPilot", conn=conn)
    pf = json.loads(req["messages"][0]["content"])["past_feedback"]
    assert pf[0]["criterion"] == "T1" and "traction is paid pilots" in pf[0]["reasons"][0]
    assert "not rules" in req["system"]
    assert "past_feedback" not in json.loads(runner.build_request("scoring", "CAPilot")["messages"][0]["content"])


# ---- email edits -------------------------------------------------------------------------------------
@needs_data
def test_email_edit_keeps_the_system_draft_and_one_reason_per_edit(conn):
    oid = draft(conn)
    e1 = outreach.edit_draft(conn, oid, "Hi Asha,\nSaw your 38 plant visits; we'd like to talk.\nRiya", "Riya", "opener should cite their own number")
    outreach.edit_draft(conn, oid, "Hi Asha,\nSaw your 38 plant visits; we'd like to talk.\nRiya (referred by Rahul)", "Riya",
                        "Rahul referred them", scope="this_case")
    rows = conn.execute("SELECT before_body, scope, change_ratio FROM email_edits ORDER BY id").fetchall()
    assert rows[0][0].startswith("Hi Asha,\nWe'd like") and [r[1] for r in rows] == ["general", "this_case"]
    assert 0 < rows[0][2] < 1
    for bad in (dict(reason="two\nlines"), dict(reason=" "), dict(scope="always")):
        with pytest.raises(outreach.OutreachError):
            outreach.edit_draft(conn, oid, "new", "Riya", **{"reason": "x", **bad})
    with pytest.raises(outreach.OutreachError, match="nothing changed"):
        outreach.edit_draft(conn, oid, conn.execute("SELECT body FROM outbox WHERE id=?", (oid,)).fetchone()[0], "Riya", "x")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE email_edits SET reason='y' WHERE id=?", (e1,))
    outreach.approve_email(conn, oid, "Riya")
    with pytest.raises(outreach.OutreachError, match="only drafts"):
        outreach.edit_draft(conn, oid, "late change", "Riya", "x")


@needs_data
def test_email_signal_measures_what_riya_changed(conn):
    a, b = draft(conn), draft(conn, "Settlr")
    outreach.edit_draft(conn, a, "Completely different text written by Riya herself.", "Riya", "too generic")
    for oid in (a, b):
        outreach.approve_email(conn, oid, "Riya")
    s = learning.email_signal(conn, config.load())
    assert s["approved_emails"] == 2 and s["edited"] == 1 and 0.25 < s["rate"] < 0.5   # one rewrite, one as drafted


# ---- disagreement -------------------------------------------------------------------------------------
@needs_data
def test_band_signal_counts_partner_review_separately(conn):
    for co, band, dec in (("CAPilot", "pass", "pass"), ("Settlr", "pass", "call"), ("Pumpwise", "partner_review", "call")):
        oid = conn.execute("INSERT INTO outcomes (company, model_band, model_recommendation) VALUES (?, ?, 'x')", (co, band)).lastrowid
        conn.execute("UPDATE outcomes SET human_decision=?, decided_by='Kushal', decided_at='2026-12-01', reason='r' WHERE id=?", (dec, oid))
    s = learning.band_signal(conn, config.load())
    assert s["compared"] == 2 and s["rate"] == 0.5 and s["partner_review_decided"] == 1


def test_plateau_needs_enough_months():
    cfg = config.load()
    assert learning.plateau([{"rate": 0.5}, {"rate": 0.5}], cfg) is None
    p = learning.plateau([{"rate": 0.9}, {"rate": 0.62}, {"rate": 0.6}, {"rate": 0.61}], cfg)
    assert p["plateaued"] and p["rates"] == [0.62, 0.6, 0.61]


@needs_data
def test_empty_feedback_is_reported_not_imputed(conn):
    d = learning.disagreement(conn)
    assert d["band"]["rate"] is None and d["criteria"]["rate"] is None and d["email"]["rate"] is None
    assert {s["sector"] for s in d["cold_sectors"]}                       # every sector is cold before any feedback
    r = learning.readiness(conn, dis=d)
    assert r["ready"] is False and r["bar_is_proposal"] and r["verdict"].startswith("Not yet")


# ---- dataset ------------------------------------------------------------------------------------------
@needs_data
def test_export_uses_live_prompt_applies_corrections_and_splits(conn, tmp_path):
    for co in FINTECH + ("CAPilot", "Pumpwise"):
        correct(conn, co)
    cfg = copy.deepcopy(config.load())
    cfg["finetune"]["max_sector_share"] = 1.0
    m = learning.export(conn, cfg, out=tmp_path)
    assert m["pairs"] == 4 and sum(m["split"].values()) == 4 and m["by_task"] == {"scoring": 4}
    row = json.loads((tmp_path / "train.jsonl").read_text().splitlines()[0])
    assert [x["role"] for x in row["messages"]] == ["system", "user", "assistant"]
    assert "Corrected by Riya" in row["messages"][2]["content"]
    assert row["messages"][0]["content"] == runner.build_request("scoring", "CAPilot")["system"]


@needs_data
def test_export_caps_a_dominant_sector(conn, tmp_path):
    for co in FINTECH + ("CAPilot", "Pumpwise"):                   # 3 fintech, 1 deeptech
        correct(conn, co)
    m = learning.export(conn, out=tmp_path)                        # cap 40% of 4 = 1 per sector
    assert m["by_sector"].get("fintech", 0) <= 1 and len(m["dropped_for_sector_cap"]) >= 2
