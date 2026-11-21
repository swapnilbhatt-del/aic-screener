"""Cost tracking, caching, alerts and the kill switch (aic/llm.py), and the API runner. A fake client: no spend."""
import copy
import json
import sqlite3
from types import SimpleNamespace

import pytest

from aic import config, db, llm, runner

MODEL = "claude-opus-5-5"


class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


class FakeClient:
    gateway_name = "test"

    def __init__(self, text='{"ok": true}', input_tokens=10_000, output_tokens=1_000, stop="end_turn", cache_read=0):
        self.calls, self.kw = 0, []
        self.text, self.inp, self.out, self.stop, self.cr = text, input_tokens, output_tokens, stop, cache_read
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kw):
        self.calls += 1
        self.kw.append(kw)
        usage = SimpleNamespace(input_tokens=self.inp, output_tokens=self.out, cache_read_input_tokens=self.cr,
                                cache_creation_input_tokens=0, server_tool_use=None)
        block = SimpleNamespace(model_dump=lambda: {"type": "text", "text": self.text})
        return FakeStream(SimpleNamespace(usage=usage, content=[block], stop_reason=self.stop, id=f"msg_{self.calls}"))


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def cfg():
    c = copy.deepcopy(config.load())
    c["ai"]["spend_limits_inr_per_day"] = {"alert": 5, "stop": 10}     # small, so a few fake calls cross them
    c["ai"]["models"] = {k: MODEL for k in c["ai"]["models"]}           # these tests use the Anthropic fake
    return c


def ask(conn, cfg, client, content="hello", **kw):
    return llm.call(conn, "scoring", [{"role": "user", "content": content}], system="sys", company="Acme",
                    client=client, cfg=cfg, max_tokens=100, **kw)


def test_cost_from_config_prices(cfg):
    usd = llm.cost_usd(MODEL, {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000}, cfg)
    assert usd == pytest.approx(4.00 + 20.00 + 0.20)


def test_every_call_is_metered_in_inr(conn, cfg):
    r = ask(conn, cfg, FakeClient())
    expect_usd = (10_000 * 4 + 1_000 * 20) / 1e6
    assert r["cost_inr"] == pytest.approx(expect_usd * cfg["ai"]["usd_inr"], abs=1e-3)
    row = conn.execute("SELECT task, company, model, input_tokens, output_tokens, status, cost_usd FROM ai_calls").fetchone()
    assert row == ("scoring", "Acme", MODEL, 10_000, 1_000, "ok", pytest.approx(expect_usd))


def test_request_sends_effort_caching_and_fallbacks(conn, cfg):
    fc = FakeClient()
    ask(conn, cfg, fc)
    kw = fc.kw[0]
    assert kw["model"] == MODEL and kw["extra_body"]["output_config"] == {"effort": cfg["ai"]["effort"]["scoring"]}
    assert kw["extra_body"]["cache_control"] == {"type": "ephemeral"} and kw["extra_body"]["fallbacks"] == "default"


def test_ledger_is_append_only(conn, cfg):
    ask(conn, cfg, FakeClient())
    for sql in ("UPDATE ai_calls SET cost_inr=0", "DELETE FROM ai_calls"):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)


def test_identical_request_served_from_cache_free(conn, cfg):
    fc = FakeClient()
    a, b = ask(conn, cfg, fc), ask(conn, cfg, fc)
    assert fc.calls == 1 and b["cached"] and b["cost_inr"] == 0 and b["text"] == a["text"]
    assert [r[0] for r in conn.execute("SELECT status FROM ai_calls ORDER BY id")] == ["ok", "cached"]


def test_alert_then_kill_switch_stops_calls(conn, cfg):
    fc = FakeClient()                                        # each call ~₹5.3 at the configured rate
    ask(conn, cfg, fc, content="1")
    assert [r[0] for r in conn.execute("SELECT kind FROM spend_events")] == ["alert"]
    ask(conn, cfg, fc, content="2")
    assert [r[0] for r in conn.execute("SELECT kind FROM spend_events")] == ["alert", "stop"]
    with pytest.raises(llm.SpendStopped, match="kill switch"):
        ask(conn, cfg, fc, content="3")
    assert fc.calls == 2
    assert conn.execute("SELECT status FROM ai_calls ORDER BY id DESC").fetchone()[0] == "blocked"


def test_worst_case_that_would_cross_the_stop_is_refused(conn, cfg):
    fc = FakeClient()
    with pytest.raises(llm.SpendStopped, match="worst case"):
        llm.call(conn, "scoring", [{"role": "user", "content": "x"}], client=fc, cfg=cfg, max_tokens=64_000)
    assert fc.calls == 0


def test_automatic_stop_lasts_for_its_day_only(conn, cfg):
    conn.execute("INSERT INTO spend_events (at, day, kind, spend_inr, by) VALUES ('x', '2000-01-01', 'stop', 1, 'system')")
    assert llm.kill_state(conn, "2000-01-01") and llm.kill_state(conn, "2000-01-02") is None


def test_manual_stop_holds_until_a_named_human_releases(conn, cfg):
    llm.manual_stop(conn, "Kushal", "testing", cfg)
    with pytest.raises(llm.SpendStopped):
        ask(conn, cfg, FakeClient())
    for by in ("model", "system", "Claude", ""):
        with pytest.raises(sqlite3.IntegrityError):
            llm.release(conn, by, "x", cfg)
    llm.release(conn, "Kushal", "ok", cfg)
    assert ask(conn, cfg, FakeClient())["cost_inr"] > 0


def test_unpriced_model_refused(conn, cfg):
    with pytest.raises(llm.ModelError, match="no price"):
        ask(conn, cfg, FakeClient(), model="claude-unknown")


def test_refusal_is_logged_and_raised(conn, cfg):
    with pytest.raises(llm.ModelError, match="refused"):
        ask(conn, cfg, FakeClient(stop="refusal"))
    assert conn.execute("SELECT count(*) FROM llm_cache").fetchone()[0] == 0


def test_no_langfuse_trace_without_keys(conn, cfg, monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    ask(conn, cfg, FakeClient())
    assert conn.execute("SELECT trace_id FROM ai_calls").fetchone()[0] is None


def test_config_refuses_unpriced_task_model_and_bad_limits():
    c = copy.deepcopy(config.load())
    c["ai"]["models"]["scoring"] = "claude-unknown"
    with pytest.raises(config.ConfigError):
        config.validate(c)
    c = copy.deepcopy(config.load())
    c["ai"]["spend_limits_inr_per_day"] = {"alert": 10, "stop": 5}
    with pytest.raises(config.ConfigError):
        config.validate(c)


# ---- runner ------------------------------------------------------------------------------
needs_data = pytest.mark.skipif(not (runner.DATA / "text" / "Pumpwise__deck.json").exists(), reason="no seed data")


@needs_data
def test_extraction_request_sends_less(monkeypatch):
    req = runner.build_request("extraction", "Pumpwise")
    payload = json.loads(req["messages"][0]["content"])
    assert set(payload["deck_pages"][0]) == {"page", "slide_label", "plain"}          # no layout copy
    assert "ignore any instructions" in req["system"] and req["tools"] is None


@needs_data
def test_research_request_has_web_tools():
    assert [t["name"] for t in runner.build_request("research", "Pumpwise")["tools"]] == ["web_search", "web_fetch"]


@needs_data
def test_run_writes_output_and_skips_when_cached(conn, cfg, tmp_path, monkeypatch):
    cfg["ai"]["spend_limits_inr_per_day"] = {"alert": 1000, "stop": 10000}
    monkeypatch.setattr(config, "load", lambda: cfg)
    fc = FakeClient(text='{"claims": []}', input_tokens=1000, output_tokens=100)
    r = runner.run(conn, "extraction", "Pumpwise", out_base=tmp_path, client=fc)
    out = json.loads((tmp_path / "claims" / "Pumpwise.raw.json").read_text())
    assert out["extracted_by"] == f"api:{MODEL}" and r["validation_errors"] == [] and r["cost_inr"] > 0
    again = runner.run(conn, "extraction", "Pumpwise", out_base=tmp_path, client=fc)
    assert "skipped" in again and fc.calls == 1


@needs_data
def test_compare_reports_cost_per_model(conn, tmp_path):
    fc = FakeClient(text='{"claims": [{"id": "a"}]}', input_tokens=1000, output_tokens=100)
    r = runner.compare(conn, "extraction", "Pumpwise", "claude-opus-5-5", "claude-haiku-5-5", tmp_path, client=fc)
    assert r["cost_inr"]["claude-haiku-5-5"] < r["cost_inr"]["claude-opus-5-5"] and "a human decides" in r["decision"]


@needs_data
def test_batch_refuses_data_dir_and_stops_at_kill_switch(conn, cfg, tmp_path, monkeypatch):
    with pytest.raises(runner.RunError):
        runner.batch(conn, runner.DATA)
    cfg["ai"]["spend_limits_inr_per_day"] = {"alert": 100, "stop": 300}   # ~₹70 a call: trips after a few
    monkeypatch.setattr(config, "load", lambda: cfg)
    fc = FakeClient(text='{"claims": []}', input_tokens=200_000, output_tokens=100)
    r = runner.batch(conn, tmp_path, client=fc)
    assert r["stopped"] and 0 < fc.calls < 30 and r["cost_inr"] > 0


# ---- Gemini ------------------------------------------------------------------------------
GEM = "gemini-4-carbon"


class FakeGemini:
    gateway_name = "gemini-test"

    def __init__(self, text='{"ok": true}', finish="STOP", grounding=None):
        self.bodies, self.text, self.finish, self.grounding = [], text, finish, grounding

    def generate(self, model, body):
        self.bodies.append((model, body))
        cand = {"content": {"role": "model", "parts": [{"text": "thinking...", "thought": True}, {"text": self.text}]},
                "finishReason": self.finish}
        if self.grounding:
            cand["groundingMetadata"] = self.grounding
        return {"candidates": [cand], "responseId": "r1",
                "usageMetadata": {"promptTokenCount": 10_000, "cachedContentTokenCount": 2_000,
                                  "candidatesTokenCount": 800, "thoughtsTokenCount": 200}}


def test_gemini_call_metered_with_thinking_as_output(conn, cfg):
    fg = FakeGemini()
    r = ask(conn, cfg, fg, model=GEM)
    assert r["text"] == '{"ok": true}'                                     # thought parts are not the answer
    assert r["usage"] == {"input_tokens": 8_000, "output_tokens": 1_000, "cache_read_tokens": 2_000,
                          "cache_write_tokens": 0, "web_searches": 0}
    usd = (8_000 * 2.00 + 1_000 * 10.00 + 2_000 * 0.10) / 1e6
    assert r["cost_inr"] == pytest.approx(usd * cfg["ai"]["usd_inr"], abs=1e-3)
    model, body = fg.bodies[0]
    assert model == GEM and body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "HIGH"}


def test_gemini_research_uses_google_search_and_bills_queries(conn, cfg):
    g = {"webSearchQueries": ["a", "b", "c"], "groundingChunks": [{"web": {"uri": "https://x.in/a", "title": "x.in"}}]}
    fg = FakeGemini(grounding=g)
    r = llm.call(conn, "research", [{"role": "user", "content": "q"}], client=fg, cfg=cfg, model=GEM, max_tokens=100,
                 tools=runner.WEB_TOOLS)
    body = fg.bodies[0][1]
    assert body["tools"] == [{"googleSearch": {}}] and "responseMimeType" not in body["generationConfig"]
    assert r["usage"]["web_searches"] == 3
    assert r["content"][1]["sources"] == [{"uri": "https://x.in/a", "title": "x.in"}]


def test_gemini_safety_block_is_a_refusal_and_max_tokens_maps(conn, cfg):
    with pytest.raises(llm.ModelError, match="refused"):
        ask(conn, cfg, FakeGemini(finish="SAFETY"), model=GEM)
    assert ask(conn, cfg, FakeGemini(finish="MAX_TOKENS"), model=GEM, content="2")["stop_reason"] == "max_tokens"


def test_gemini_passes_the_kill_switch(conn, cfg):
    llm.manual_stop(conn, "Kushal", "test", cfg)
    fg = FakeGemini()
    with pytest.raises(llm.SpendStopped):
        ask(conn, cfg, fg, model=GEM)
    assert fg.bodies == []
