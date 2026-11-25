"""Case 04 / Build 5: prompt audit and redaction, queue + volume test, prompt versions, hand-over page."""
import json
import sqlite3

import pytest

from aic import audit, db, handover, llm, queue, runner
from tests.test_llm import FakeGemini

needs_data = pytest.mark.skipif(not (runner.DATA / "scores" / "raw" / "CAPilot.json").exists(), reason="no seed data")


# ---- Task 1: nothing personal leaves the machine -----------------------------------------------------------
def test_redaction_replaces_emails_and_phones_but_not_numbers():
    (out,), n = llm.redact(["write to a.b@x.in or +91 98765 43210; ARR 6600000000.0"])
    assert n == 2 and "@" not in out and "98765" not in out and "6600000000.0" in out
    assert llm.redact(["a.b@x.in"])[0] == llm.redact(["A.B@x.in"])[0]           # same person, same token


def test_redaction_keeps_json_payloads_valid():
    payload = json.dumps({"plain": "Thank you\nYatrika 11\nhello@yatrika.example"})
    (out,), n = llm.redact([payload])
    assert n == 1 and json.loads(out)["plain"].endswith("[email:1d4c122b]")     # the \n escape survives


def test_every_call_is_redacted_before_it_is_sent_and_logged(tmp_path):
    conn = db.connect(":memory:")
    fg = FakeGemini()
    llm.call(conn, "drafting", [{"role": "user", "content": "founder: riya@aic.vc"}], system="s", model="gemini-4-carbon",
             client=fg, max_tokens=100, prompt_ver="x.md@1")
    sent = fg.bodies[0][1]["contents"][0]["parts"][0]["text"]
    assert "riya@aic.vc" not in sent and "[email:" in sent
    assert conn.execute("SELECT pii_redacted, prompt_version FROM ai_calls").fetchone() == (1, "x.md@1")


@needs_data
def test_audit_covers_every_call_and_sends_no_personal_data():
    a = audit.build()
    calls = {c["call"] for c in a["calls"]}
    assert {"extraction", "research", "scoring (full card)", "scoring (one criterion)"} <= calls
    assert all(c["pii_sent"] == 0 and c["sent_chars"] < c["available_chars"] for c in a["calls"])


# ---- Task 2: queue and volume test ---------------------------------------------------------------------------
def test_jobs_cannot_disappear_and_attention_needs_a_reason():
    conn = db.connect(":memory:")
    queue.enqueue(conn, "b", [{"label": "A#1", "company": "A"}])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM jobs")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE jobs SET status='needs_attention', reason=' '")


@needs_data
def test_volume_test_accounts_for_every_application(tmp_path):
    r = queue.volume_test(20, workers=4, out=tmp_path / "vt", send_traces=False)
    assert r["enqueued"] == 20 and r["lost"] == 0 and r["running"] == 0
    assert r["scored"] + r["queued"] + r["needs_attention"] == 20
    assert r["peak_in_flight"] <= 4
    p1 = r["phases"][0]
    assert p1["queued"] > 0 and p1["queued_reasons"] == ["paused before scoring"]   # the daily stop paused the queue
    att = {j["label"]: j["reason"] for j in r["jobs"] if j["status"] == "needs_attention"}
    assert set(att) == {"EarnWise#2", "GrainKind#2", "Pumpwise#2", "RentRoute#2", "Settlr#2"} and all(att.values())
    capilot = next(j for j in r["jobs"] if j["label"] == "CAPilot#2")
    assert capilot["status"] == "scored" and capilot["attempts"] == 2          # a transient 503 was retried


@needs_data
def test_runs_record_their_prompt_version(tmp_path):
    conn = db.connect(":memory:")
    fg = FakeGemini(text=json.dumps({"claims": []}))
    r = runner.run(conn, "extraction", "CAPilot", force=True, out_base=tmp_path, client=fg, model="gemini-4-carbon")
    assert r["prompt_version"].startswith("extract_claims.md@")
    assert conn.execute("SELECT prompt_version FROM ai_calls").fetchone()[0] == r["prompt_version"]


def test_portkey_retries_are_configured():
    h = json.loads(llm.portkey_config_header())
    assert h["retry"]["attempts"] >= 1 and 503 in h["retry"]["on_status_codes"]


# ---- the page --------------------------------------------------------------------------------------------------
@needs_data
def test_handover_answers_all_five_questions_and_every_pain_point():
    h = handover.build()
    assert sorted({q["n"] for q in h["questions"]}) == [1, 2, 3, 4, 5]
    assert all(q["status"] in ("done", "partial", "blocked") and q["evidence"] for q in h["questions"])
    assert len(h["pains"]) >= 10 and all(p["status"] != "partial" or p["gap"] for p in h["pains"])   # gaps are stated
