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


# ---- Unsloth notebook -----------------------------------------------------------------------------------
NB = learning.ROOT / "notebooks" / "unsloth_finetune.ipynb"


def _cells():
    nb = json.loads(NB.read_text())
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def _python(src):          # notebook magics and shell lines become `pass`; the rest must be plain Python
    out = []
    for l in src.splitlines():
        body = l.lstrip()
        out.append(l[:len(l) - len(body)] + "pass" if body.startswith(("!", "%")) else l)
    return "\n".join(out)


def test_notebook_cells_are_valid_python():
    for src in _cells():
        compile(_python(src), "<cell>", "exec")


def test_notebook_reads_the_bar_from_the_manifest_not_hardcoded():
    text = "".join(_cells())
    assert 'BAR = manifest["bar"]["disagreement_above"]' in text
    assert text.count('"disagreement_above": 0.30') == 1         # only the made-up smoke-test manifest
    assert "BAR =" not in text.replace('BAR = manifest["bar"]["disagreement_above"]', "")


def test_notebook_smoke_data_and_task_detection(tmp_path):
    settings, data = _cells()[1], _cells()[2]
    ns = {}
    exec(_python(settings).replace("SMOKE_TEST = False", "SMOKE_TEST = True")
         .replace('DATA_DIR = "/content/finetune"', f'DATA_DIR = "{tmp_path}"'), ns)
    exec(_python(data), ns)
    assert (len(ns["train"]), len(ns["val"]), len(ns["test"])) == (45, 9, 6) and ns["BAR"] == 0.30
    email = {"messages": [{"role": "system", "content": "Rewrite this All In Capital outreach draft the way Riya would send it."}]}
    assert ns["task_of"](email) == "email" and ns["task_of"](ns["train"][0]) == "scoring"


@needs_data
def test_notebook_task_detection_matches_the_export(conn):
    oid = draft(conn)
    outreach.approve_email(conn, oid, "Riya")
    pair = [p for p in learning.build_pairs(conn, config.load()) if p["task"] == "email"][0]
    assert "Rewrite this All In Capital outreach draft" in "".join(_cells()[2])
    assert pair["messages"][0]["content"].startswith("Rewrite this All In Capital outreach draft")


# ---- per-criterion pairs ----------------------------------------------------------------------------------
@needs_data
def test_criterion_request_takes_only_its_mapped_inputs_and_fits():
    cfg = config.load()
    t1 = json.loads(runner.build_criterion_request("Pumpwise", "T1", cfg)["messages"][0]["content"])
    assert t1["claims"] and all(c["metric"].startswith("customers_") or c["metric"] in cfg["finetune"]["criterion_inputs"]["T1"]["claims"]
                                for c in t1["claims"])
    assert "fund_research" not in t1 and "form_founders" not in t1
    f3 = json.loads(runner.build_criterion_request("Pumpwise", "F3", cfg)["messages"][0]["content"])
    assert len(f3["claims"]) > len(t1["claims"])                    # F3 (candour) reads every claim
    sysmsg = runner.build_criterion_request("Pumpwise", "M3", cfg)["system"]
    assert sysmsg.startswith(runner.CRITERION_MARK) and "| M3 |" in sysmsg and "| T1 |" not in sysmsg
    for co in runner.companies():                                   # ~3.3 chars/token: fits 8192 with the answer
        for k in cfg["criteria"]:
            r = runner.build_criterion_request(co, k, cfg)
            assert len(r["system"]) + len(r["messages"][0]["content"]) < 25_000, (co, k)


@needs_data
def test_per_criterion_export_applies_the_correction_to_its_criterion(conn, tmp_path):
    correct(conn, "Settlr", "T1")
    cfg = copy.deepcopy(config.load())
    m = learning.export(conn, cfg, out=tmp_path, per_criterion=True)
    rows = [json.loads(l) for f in ("train", "val", "test") for l in (tmp_path / f"{f}.jsonl").read_text().splitlines()]
    assert m["pairs"] == 12 and m["granularity"] == "per_criterion" and len(rows) == 12
    t1 = [r for r in rows if json.loads(r["messages"][2]["content"])["criterion"] == "T1"][0]
    ans = json.loads(t1["messages"][2]["content"])
    human = conn.execute("SELECT human_score FROM corrections").fetchone()[0]
    assert ans["score"] == human and "Corrected by Riya" in ans["rationale"]


def test_notebook_evaluation_scores_both_formats_with_a_fake_model(tmp_path):
    import types
    c = _cells()
    ns = {"model": None}
    exec(_python(c[1]).replace("SMOKE_TEST = False", "SMOKE_TEST = True").replace('"/content/finetune"', repr(str(tmp_path))), ns)
    exec(_python(c[2]), ns)
    ns["FastLanguageModel"] = types.SimpleNamespace(for_inference=lambda m: None)
    exec(_python(c[4]).replace('baseline = evaluate(test, "baseline (untuned)") if test else None', ""), ns)
    rows = ns["test"]
    assert {("criteria" in json.loads(r["messages"][2]["content"])) for r in rows} == {True, False}   # both formats present
    ns["generate"] = lambda m, n: next("ok " + r["messages"][2]["content"] for r in rows if r["messages"][:2] == m)
    good = ns["evaluate"](rows, "perfect")
    ns["generate"] = lambda m, n: "not json"
    bad = ns["evaluate"](rows, "broken")
    assert good["scoring"]["disagreement"] == 0 and bad["scoring"]["disagreement"] == 1 and bad["scoring"]["valid_json"] == 0
    ns["SMOKE_TEST"] = False
    exec(_python(c[7]).split("summary =")[0].replace('tuned = evaluate(test, "fine-tuned") if test else None', ""), ns)
    assert "clears the bar" in ns["verdict"](bad, good) and "do not deploy" in ns["verdict"](good, bad)
