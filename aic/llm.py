"""One door for every model call: metered, cached, capped, traced.

Why (lecture, 19 Nov): before production you must know where every rupee goes; only then can you alert,
cap and kill. Every call made by the pipeline goes through `call()`:

  1. kill switch: refused if today's spend reached `ai.spend_limits_inr_per_day.stop`, if a partner pulled the
     manual stop, or if this call's worst case would cross the stop. A refused call is still logged ('blocked').
  2. cache: an identical request (model, system, messages, tools, effort) is served from `llm_cache` at no cost.
  3. call: by model name. `claude-*` -> Anthropic Messages API (official SDK), via Portkey when PORTKEY_API_KEY
     is set. `gemini-*` -> Gemini: through Portkey (OpenAI-compatible, provider google) when PORTKEY_API_KEY is
     set, else direct generateContent (GEMINI_API_KEY). Research needs Google Search grounding, so it always goes direct.
  4. meter: tokens and cost (USD and INR, prices from config) appended to `ai_calls` (append-only ledger).
  5. alert: crossing `alert` records an alert event; crossing `stop` engages the kill switch for the day.
  6. trace: a Langfuse trace + generation when LANGFUSE_PUBLIC_KEY/SECRET_KEY are set (never blocks the call).

Keys come from the environment or a gitignored `.env` (see `.env.example`). Nothing here runs without a key.

  python -m aic.llm spend                       today's and total spend, per task and model
  python -m aic.llm stop <your name> "<why>"    pull the kill switch now
  python -m aic.llm release <your name> "<why>" release it (a named human only; DB-enforced)
  python -m aic.llm check                       one tiny metered call: shows the route (portkey/gemini/anthropic) and Langfuse trace id
"""
import base64
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import config, db

ROOT = Path(__file__).resolve().parent.parent
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class SpendStopped(RuntimeError):
    pass


class ModelError(RuntimeError):
    pass


# ---- environment ---------------------------------------------------------------------
def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=value lines). Existing environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def gateway() -> str:
    return "portkey" if os.environ.get("PORTKEY_API_KEY") else "anthropic"


def make_client():
    """Official Anthropic SDK client; through Portkey when PORTKEY_API_KEY is set."""
    import anthropic
    if os.environ.get("PORTKEY_API_KEY"):
        headers = {"x-portkey-api-key": os.environ["PORTKEY_API_KEY"], "x-portkey-provider": "anthropic"}
        if os.environ.get("PORTKEY_VIRTUAL_KEY"):
            headers["x-portkey-virtual-key"] = os.environ["PORTKEY_VIRTUAL_KEY"]
        return anthropic.Anthropic(base_url=os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai"),
                                   api_key=os.environ.get("ANTHROPIC_API_KEY", "via-portkey-virtual-key"),
                                   default_headers=headers)
    return anthropic.Anthropic()


def provider(model: str) -> str:
    return "gemini" if model.startswith("gemini-") else "anthropic"


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_FINISH = {"STOP": "end_turn", "MAX_TOKENS": "max_tokens", "SAFETY": "refusal", "PROHIBITED_CONTENT": "refusal",
                 "BLOCKLIST": "refusal", "SPII": "refusal", "RECITATION": "refusal"}
GEMINI_THINKING = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH"}


class GeminiClient:
    """Gemini REST (generateContent) with the API key in the x-goog-api-key header. No SDK dependency."""
    gateway_name = "gemini"

    def __init__(self, key: Optional[str] = None):
        self.key = key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self.key:
            raise ModelError("GEMINI_API_KEY is not set (.env)")

    def generate(self, model: str, body: dict, timeout: int = 300, retries: int = 4) -> dict:
        """Retries only 'busy' (503) and rate-limit (429) answers, with backoff; nothing is billed for those.
        A 429 whose quota limit is 0 (model not available on this key's tier) is not retried."""
        for attempt in range(retries + 1):
            req = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": self.key})
            try:
                return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            except urllib.error.HTTPError as e:
                msg = e.read()[:800]
                if e.code in (429, 503) and b"limit: 0" not in msg and attempt < retries:
                    wait = 30 * 2 ** attempt
                    print(f"Gemini {e.code}, retry {attempt + 1}/{retries} in {wait}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise ModelError(f"Gemini HTTP {e.code}: {msg!r}") from None


def gemini_body(system: Any, messages: list, tools: Optional[list], max_tokens: int, effort: Optional[str]) -> dict:
    """Anthropic-shaped request -> Gemini generateContent body. Web tools become Google Search grounding."""
    def text_of(c):
        if isinstance(c, str):
            return c
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    body: Dict[str, Any] = {
        "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": text_of(m["content"])}]}
                     for m in messages],
        "generationConfig": {"maxOutputTokens": max_tokens}}
    if system is not None:
        body["systemInstruction"] = {"parts": [{"text": system if isinstance(system, str) else text_of(system)}]}
    if effort in GEMINI_THINKING:
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": GEMINI_THINKING[effort]}
    if tools and any(t.get("name") in ("web_search", "web_fetch") for t in tools):
        body["tools"] = [{"googleSearch": {}}]
    else:
        body["generationConfig"]["responseMimeType"] = "application/json"
    return body


def gemini_result(resp: dict) -> dict:
    """Gemini response -> the same shape `call()` returns for Anthropic (text, content, stop_reason, usage)."""
    cand = (resp.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    u = resp.get("usageMetadata") or {}
    cached = u.get("cachedContentTokenCount", 0) or 0
    gm = cand.get("groundingMetadata") or {}
    usage = {"input_tokens": (u.get("promptTokenCount", 0) or 0) - cached + (u.get("toolUsePromptTokenCount", 0) or 0),
             "output_tokens": (u.get("candidatesTokenCount", 0) or 0) + (u.get("thoughtsTokenCount", 0) or 0),
             "cache_read_tokens": cached, "cache_write_tokens": 0,
             "web_searches": len(gm.get("webSearchQueries") or [])}
    content = [{"type": "text", "text": text}]
    if gm:
        content.append({"type": "grounding", "queries": gm.get("webSearchQueries") or [],
                        "sources": [{"uri": c["web"].get("uri"), "title": c["web"].get("title")}
                                    for c in gm.get("groundingChunks") or [] if c.get("web")]})
    reason = cand.get("finishReason") or ("refusal" if (resp.get("promptFeedback") or {}).get("blockReason") else "OTHER")
    return {"text": text, "content": content, "stop_reason": GEMINI_FINISH.get(reason, reason.lower()),
            "usage": usage, "id": resp.get("responseId")}


# ---- Gemini through Portkey (OpenAI-compatible gateway) -----------------------------------------------
PORTKEY_CHAT = "/v1/chat/completions"
OPENAI_FINISH = {"stop": "end_turn", "length": "max_tokens", "content_filter": "refusal"}


def uses_web_tools(tools: Optional[list]) -> bool:
    return bool(tools) and any(t.get("name") in ("web_search", "web_fetch") for t in tools)


def gemini_via_portkey(tools: Optional[list]) -> bool:
    """Gemini goes through Portkey when a Portkey key is set, except calls that need Google Search grounding
    (research): Portkey's OpenAI-compatible route does not carry it, so those stay direct."""
    return bool(os.environ.get("PORTKEY_API_KEY")) and not uses_web_tools(tools)


class PortkeyGeminiClient:
    """Portkey's OpenAI-compatible /v1/chat/completions with provider 'google'.
    Auth: x-portkey-api-key, plus either a Portkey virtual key or the Gemini key as a bearer token."""
    gateway_name = "portkey"

    def __init__(self):
        self.key = os.environ.get("PORTKEY_API_KEY")
        if not self.key:
            raise ModelError("PORTKEY_API_KEY is not set (.env)")
        self.base = os.environ.get("PORTKEY_BASE_URL", "https://api.portkey.ai").rstrip("/")
        self.headers = {"Content-Type": "application/json", "x-portkey-api-key": self.key, "x-portkey-provider": "google"}
        if os.environ.get("PORTKEY_VIRTUAL_KEY"):
            self.headers["x-portkey-virtual-key"] = os.environ["PORTKEY_VIRTUAL_KEY"]
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            self.headers["Authorization"] = "Bearer " + (os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"])
        else:
            raise ModelError("Portkey needs PORTKEY_VIRTUAL_KEY or GEMINI_API_KEY for Google")

    def chat(self, body: dict, timeout: int = 300, retries: int = 4) -> dict:
        for attempt in range(retries + 1):
            req = urllib.request.Request(self.base + PORTKEY_CHAT, data=json.dumps(body).encode(), method="POST",
                                         headers=self.headers)
            try:
                return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
            except urllib.error.HTTPError as e:
                msg = e.read()[:800]
                if e.code in (429, 503) and b"limit: 0" not in msg and attempt < retries:
                    wait = 30 * 2 ** attempt
                    print(f"Portkey {e.code}, retry {attempt + 1}/{retries} in {wait}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise ModelError(f"Portkey HTTP {e.code}: {msg!r}") from None


def openai_body(model: str, system: Any, messages: list, max_tokens: int) -> dict:
    def text_of(c):
        if isinstance(c, str):
            return c
        return "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    msgs = [{"role": "system", "content": system if isinstance(system, str) else text_of(system)}] if system is not None else []
    msgs += [{"role": m["role"], "content": text_of(m["content"])} for m in messages]
    return {"model": model, "messages": msgs, "max_tokens": max_tokens}


def openai_result(resp: dict) -> dict:
    """OpenAI-shaped response -> the same shape call() returns for the other providers."""
    ch = (resp.get("choices") or [{}])[0]
    text = (ch.get("message") or {}).get("content") or ""
    u = resp.get("usage") or {}
    cached = ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    usage = {"input_tokens": (u.get("prompt_tokens") or 0) - cached, "output_tokens": u.get("completion_tokens") or 0,
             "cache_read_tokens": cached, "cache_write_tokens": 0, "web_searches": 0}
    fin = ch.get("finish_reason") or "other"
    return {"text": text, "content": [{"type": "text", "text": text}], "stop_reason": OPENAI_FINISH.get(fin, fin),
            "usage": usage, "id": resp.get("id")}


# ---- money -----------------------------------------------------------------------------
def today(cfg: dict, now: Optional[datetime] = None) -> str:
    return (now or datetime.now(ZoneInfo(cfg["ai"]["day_tz"]))).astimezone(ZoneInfo(cfg["ai"]["day_tz"])).date().isoformat()


def cost_usd(model: str, usage: Dict[str, int], cfg: dict) -> float:
    p = cfg["ai"]["prices_usd_per_mtok"][model]
    return (usage.get("input_tokens", 0) * p["input"] + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_read_tokens", 0) * p["cache_read"] + usage.get("cache_write_tokens", 0) * p.get("cache_write", 0)
            ) / 1e6 + usage.get("web_searches", 0) * p.get("web_search_per_1k", cfg["ai"]["web_search_usd_per_1k"]) / 1000


def spend_inr(conn, day: Optional[str] = None) -> float:
    q, a = ("SELECT coalesce(sum(cost_inr), 0) FROM ai_calls WHERE day=?", (day,)) if day else \
        ("SELECT coalesce(sum(cost_inr), 0) FROM ai_calls", ())
    return conn.execute(q, a).fetchone()[0]


def kill_state(conn, day: str) -> Optional[dict]:
    """The latest stop/release decides. A manual stop holds until released; an automatic stop holds for its day."""
    r = conn.execute("SELECT kind, day, by, note, at FROM spend_events WHERE kind IN ('stop', 'manual_stop', 'release') "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    if not r or r[0] == "release" or (r[0] == "stop" and r[1] != day):
        return None
    return {"kind": r[0], "day": r[1], "by": r[2], "note": r[3], "at": r[4]}


def _event(conn, kind: str, day: str, spend: float, by: str, note: str = "") -> None:
    conn.execute("INSERT INTO spend_events (at, day, kind, spend_inr, by, note) VALUES (?, ?, ?, ?, ?, ?)",
                 (datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(), day, kind, round(spend, 2), by, note))
    conn.commit()


def manual_stop(conn, by: str, note: str, cfg: Optional[dict] = None) -> None:
    cfg = cfg or config.load()
    d = today(cfg)
    _event(conn, "manual_stop", d, spend_inr(conn, d), by, note)


def release(conn, by: str, note: str, cfg: Optional[dict] = None) -> None:
    cfg = cfg or config.load()
    d = today(cfg)
    _event(conn, "release", d, spend_inr(conn, d), by, note)


# ---- ledger ------------------------------------------------------------------------------
def _log(conn, cfg, *, task, company, model, gw, usage, status, latency_ms=None, request_id=None, trace_id=None,
         error=None, day=None) -> int:
    usd = cost_usd(model, usage, cfg) if status == "ok" else 0.0
    rid = conn.execute(
        "INSERT INTO ai_calls (at, day, task, company, model, gateway, input_tokens, output_tokens, cache_read_tokens, "
        "cache_write_tokens, web_searches, cost_usd, cost_inr, latency_ms, status, request_id, trace_id, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="microseconds"), day or today(cfg), task, company,
         model, gw, usage.get("input_tokens", 0), usage.get("output_tokens", 0), usage.get("cache_read_tokens", 0),
         usage.get("cache_write_tokens", 0), usage.get("web_searches", 0), round(usd, 6),
         round(usd * cfg["ai"]["usd_inr"], 4), latency_ms, status, request_id, trace_id, error)).lastrowid
    conn.commit()
    return rid


def _usage(msg) -> Dict[str, int]:
    u = msg.usage
    stu = getattr(u, "server_tool_use", None)
    return {"input_tokens": u.input_tokens or 0, "output_tokens": u.output_tokens or 0,
            "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
            "web_searches": (getattr(stu, "web_search_requests", 0) or 0) if stu else 0}


def cache_key(model: str, system: Any, messages: list, tools: Optional[list], effort: Optional[str]) -> str:
    blob = json.dumps({"m": model, "s": system, "msg": messages, "t": tools, "e": effort}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _worst_case_usd(model: str, system: Any, messages: list, max_tokens: int, cfg: dict) -> float:
    chars = len(json.dumps(system, default=str)) + len(json.dumps(messages, default=str))
    return cost_usd(model, {"input_tokens": chars // 3, "output_tokens": max_tokens}, cfg)   # ~3 chars/token, generous


# ---- tracing (Langfuse, optional) ------------------------------------------------------------
def _langfuse(task: str, company: Optional[str], model: str, usage: dict, usd: float, started: float, ended: float,
              system: Any, messages: list, output: Any) -> Optional[str]:
    """One Langfuse generation per call, sent as an OpenTelemetry span (OTLP/HTTP JSON) to
    /api/public/otel/v1/traces with `x-langfuse-ingestion-version: 4`. (The older /api/public/ingestion
    batch endpoint now answers 410 Gone on Langfuse Cloud.) Returns the trace id, or None. Never blocks a call."""
    pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        return None
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    tid, sid = uuid.uuid4().hex, uuid.uuid4().hex[:16]
    s = lambda k, v: {"key": k, "value": {"stringValue": str(v)}}
    i = lambda k, v: {"key": k, "value": {"intValue": int(v)}}
    attrs = [s("langfuse.observation.type", "generation"), s("langfuse.trace.name", f"aic.{task}"),
             s("langfuse.observation.model.name", model), s("gen_ai.request.model", model),
             s("langfuse.observation.input", json.dumps({"system": str(system)[:20000],
                                                          "messages": json.dumps(messages, default=str)[:50000]})),
             s("langfuse.observation.output", json.dumps(output, default=str)[:50000]),
             s("langfuse.observation.usage_details", json.dumps({"input": usage.get("input_tokens", 0),
                                                                  "output": usage.get("output_tokens", 0),
                                                                  "cache_read_input_tokens": usage.get("cache_read_tokens", 0)})),
             s("langfuse.observation.cost_details", json.dumps({"total": usd})),
             i("gen_ai.usage.input_tokens", usage.get("input_tokens", 0)),
             i("gen_ai.usage.output_tokens", usage.get("output_tokens", 0)),
             s("langfuse.trace.metadata.company", company or ""), s("langfuse.observation.metadata.task", task),
             {"key": "langfuse.trace.tags", "value": {"arrayValue": {"values": [{"stringValue": "aic-screener"},
                                                                                {"stringValue": task}]}}}]
    span = {"traceId": tid, "spanId": sid, "name": task, "kind": 3,
            "startTimeUnixNano": str(int(started * 1e9)), "endTimeUnixNano": str(int(ended * 1e9)),
            "attributes": attrs, "status": {"code": 1}}
    body = {"resourceSpans": [{"resource": {"attributes": [s("service.name", "aic-screener")]},
                               "scopeSpans": [{"scope": {"name": "aic.llm"}, "spans": [span]}]}]}
    req = urllib.request.Request(f"{host}/api/public/otel/v1/traces", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-langfuse-ingestion-version": "4",
                                          "Authorization": "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return tid
    except Exception as e:                                       # tracing must never break or block a call
        print(f"langfuse trace failed: {e}", file=sys.stderr)
        return None


# ---- the call ----------------------------------------------------------------------------------
def call(conn: sqlite3.Connection, task: str, messages: List[dict], system: Any = None, company: Optional[str] = None,
         tools: Optional[list] = None, max_tokens: int = 32000, model: Optional[str] = None, client=None,
         cfg: Optional[dict] = None, use_cache: bool = True) -> dict:
    """Returns {"text", "content" (list of block dicts), "stop_reason", "usage", "cost_inr", "cached", "call_id"}."""
    cfg = cfg or config.load()
    ai = cfg["ai"]
    model = model or ai["models"][task]
    effort = ai.get("effort", {}).get(task)
    if model not in ai["prices_usd_per_mtok"]:
        raise ModelError(f"no price configured for {model}; add it to ai.prices_usd_per_mtok before using it")
    d = today(cfg)
    prov = provider(model)
    if client is not None:
        gw = getattr(client, "gateway_name", "test")
    elif prov == "anthropic":
        gw = gateway()
    else:
        gw = "portkey" if gemini_via_portkey(tools) else "gemini"

    ks = kill_state(conn, d)
    spent = spend_inr(conn, d)
    worst = _worst_case_usd(model, system, messages, max_tokens, cfg) * ai["usd_inr"]
    if ks or spent + worst > ai["spend_limits_inr_per_day"]["stop"]:
        why = f"kill switch ({ks['kind']} by {ks['by']})" if ks else \
            f"today's spend ₹{spent:,.0f} + this call's worst case ₹{worst:,.0f} would cross the stop limit"
        _log(conn, cfg, task=task, company=company, model=model, gw=gw, usage={}, status="blocked", error=why, day=d)
        raise SpendStopped(why)

    key = cache_key(model, system, messages, tools, effort)
    if use_cache:
        hit = conn.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        if hit:
            r = json.loads(hit[0])
            cid = _log(conn, cfg, task=task, company=company, model=model, gw="cache", usage={}, status="cached", day=d)
            return {**r, "cost_inr": 0.0, "cached": True, "call_id": cid}

    started = time.time()
    try:
        if prov == "gemini" and (hasattr(client, "chat") if client is not None else gemini_via_portkey(tools)):
            client = client or PortkeyGeminiClient()
            r = openai_result(client.chat(openai_body(model, system, messages, max_tokens)))
            usage, content, text, stop, req_id = r["usage"], r["content"], r["text"], r["stop_reason"], r["id"]
        elif prov == "gemini":
            client = client or GeminiClient()
            r = gemini_result(client.generate(model, gemini_body(system, messages, tools, max_tokens, effort)))
            usage, content, text, stop, req_id = r["usage"], r["content"], r["text"], r["stop_reason"], r["id"]
        else:
            client = client or make_client()
            params: Dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
            if system is not None:
                params["system"] = system
            if tools:
                params["tools"] = tools
            extra: Dict[str, Any] = {"cache_control": {"type": "ephemeral"}, "fallbacks": "default"}
            if effort:
                extra["output_config"] = {"effort": effort}
            with client.messages.stream(**params, extra_body=extra, extra_headers={"anthropic-beta": FALLBACK_BETA}) as s:
                msg = s.get_final_message()
            usage = _usage(msg)
            content = [b.model_dump() if hasattr(b, "model_dump") else dict(b) for b in msg.content]
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            stop, req_id = msg.stop_reason, getattr(msg, "_request_id", None) or getattr(msg, "id", None)
    except Exception as e:
        _log(conn, cfg, task=task, company=company, model=model, gw=gw, usage={}, status="error",
             latency_ms=int((time.time() - started) * 1000), error=f"{type(e).__name__}: {e}"[:500], day=d)
        raise
    ended = time.time()
    out = {"text": text, "content": content, "stop_reason": stop, "usage": usage}
    usd = cost_usd(model, usage, cfg)
    trace = _langfuse(task, company, model, usage, usd, started, ended, system, messages, text)
    cid = _log(conn, cfg, task=task, company=company, model=model, gw=gw, usage=usage, status="ok",
               latency_ms=int((ended - started) * 1000), request_id=req_id,
               trace_id=trace, day=d)
    if use_cache and stop == "end_turn":
        conn.execute("INSERT OR REPLACE INTO llm_cache (key, model, response, created_at) VALUES (?, ?, ?, ?)",
                     (key, model, json.dumps(out), datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()))
        conn.commit()
    _check_limits(conn, cfg, d)
    if stop == "refusal":
        raise ModelError(f"model refused; logged as call {cid}")
    return {**out, "cost_inr": round(usd * ai["usd_inr"], 4), "cached": False, "call_id": cid}


def _check_limits(conn, cfg: dict, d: str) -> None:
    lim, spent = cfg["ai"]["spend_limits_inr_per_day"], spend_inr(conn, d)
    kinds = {r[0] for r in conn.execute("SELECT kind FROM spend_events WHERE day=?", (d,))}
    if spent >= lim["stop"] and "stop" not in kinds:
        _event(conn, "stop", d, spent, "system", f"daily spend reached the stop limit ₹{lim['stop']:,}")
        print(f"KILL SWITCH: AI spend today ₹{spent:,.0f} reached ₹{lim['stop']:,}; all model calls stop until tomorrow "
              "or a named human releases it (python -m aic.llm release)", file=sys.stderr)
    elif spent >= lim["alert"] and "alert" not in kinds:
        _event(conn, "alert", d, spent, "system", f"daily spend passed the alert limit ₹{lim['alert']:,}")
        print(f"ALERT: AI spend today ₹{spent:,.0f} passed ₹{lim['alert']:,}", file=sys.stderr)


def json_from(text: str) -> dict:
    """The JSON object in a model reply (the prompts ask for the file content only)."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ModelError("no JSON object in the model reply")
    return json.loads(text[a:b + 1])


# ---- CLI --------------------------------------------------------------------------------------
def spend_report(conn, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    d = today(cfg)
    q = lambda col: [dict(zip(("key", "calls", "inr", "tokens"), r)) for r in conn.execute(
        f"SELECT {col}, count(*), round(sum(cost_inr), 2), sum(input_tokens + output_tokens + cache_read_tokens) "
        f"FROM ai_calls GROUP BY {col} ORDER BY 3 DESC")]
    return {"today": d, "today_inr": round(spend_inr(conn, d), 2), "total_inr": round(spend_inr(conn), 2),
            "limits_inr": cfg["ai"]["spend_limits_inr_per_day"], "kill_switch": kill_state(conn, d),
            "by_task": q("task"), "by_model": q("model"), "by_status": q("status")}


if __name__ == "__main__":
    load_env()
    a, conn = sys.argv[1:], db.connect()
    if a[:1] == ["spend"]:
        print(json.dumps(spend_report(conn), indent=1))
    elif a[:1] == ["stop"] and len(a) == 3:
        manual_stop(conn, a[1], a[2]); print("kill switch engaged")
    elif a[:1] == ["release"] and len(a) == 3:
        release(conn, a[1], a[2]); print("kill switch released")
    elif a[:1] == ["check"]:
        r = call(conn, "drafting", [{"role": "user", "content": 'Reply with {"ok": true} only.'}], system="Reply with JSON only.",
                 max_tokens=256, use_cache=False)
        row = conn.execute("SELECT gateway, trace_id, model, input_tokens, output_tokens FROM ai_calls WHERE id=?", (r["call_id"],)).fetchone()
        print(json.dumps({"reply": r["text"][:80], "gateway": row[0], "langfuse_trace_id": row[1], "model": row[2],
                          "tokens": [row[3], row[4]], "cost_inr": r["cost_inr"],
                          "portkey_key_set": bool(os.environ.get("PORTKEY_API_KEY")),
                          "langfuse_keys_set": bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))}, indent=1))
    else:
        print(__doc__)
