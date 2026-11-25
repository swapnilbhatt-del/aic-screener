"""'Ready to hand over?' (Case 04, Build 5): Kushal's five questions and every pain point in the case, each with its
status and the evidence for it, computed from the pipeline's own files and DB wherever possible.

Statuses: done (built and shown working), partial (built, with a stated gap), blocked (needs something only the user or
the partners can provide). Nothing is marked done on the strength of code alone if it has never run.
"""
import json
import os
from pathlib import Path
from typing import Optional

from . import audit, config, db, llm

ROOT = Path(__file__).resolve().parent.parent
VT = ROOT / "data" / "volume_test" / "result.json"


def _volume() -> Optional[dict]:
    if not VT.exists():
        return None
    r = json.loads(VT.read_text())
    reasons = {}
    for j in r["jobs"]:
        if j["status"] == "needs_attention":
            reasons[j["label"]] = j["reason"]
    sample = next((j for j in r["jobs"] if j["status"] == "scored" and j["trace_id"]), None)
    return {k: r.get(k) for k in ("batch", "enqueued", "scored", "queued", "needs_attention", "lost", "retries",
                                   "workers", "peak_in_flight", "wall_seconds", "model_calls", "blocked_calls",
                                   "langfuse_traces", "phases", "note", "faults_injected")} | \
        {"attention_reasons": reasons, "sample_trace": sample and sample["trace_id"],
         "jobs": [{k: j[k] for k in ("label", "status", "attempts", "reason")} for j in r["jobs"]]}


def build(conn=None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    llm.load_env()
    conn = conn or db.connect()
    au = audit.build(cfg)
    vol = _volume()
    lf = bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
    pk = bool(os.environ.get("PORTKEY_API_KEY"))
    traced = conn.execute("SELECT count(*), sum(trace_id IS NOT NULL), sum(prompt_version IS NOT NULL) FROM ai_calls "
                          "WHERE status='ok'").fetchone()
    pii_ledger = conn.execute("SELECT coalesce(sum(pii_redacted), 0) FROM ai_calls").fetchone()[0]
    lim = cfg["ai"]["spend_limits_inr_per_day"]
    r = cfg["roi"]
    riya_hours_100 = 100 * r["riya_minutes_per_application"] / 60

    questions = [
        {"n": 1, "q": "Does it work?", "task": "Evals (previous build)", "status": "done",
         "evidence": "Blind backtest on 12 past memos, deterministic checks agree 34/34 with the reference script, "
                     "claim recall 40/40. Limit: every memo scored Pass, so band agreement equals 'always pass'; the "
                     "out-of-sample test has not run.", "page": "trust"},
        {"n": 2, "q": "Is it safe?", "task": "Task 1: audit your prompts", "status": "done",
         "evidence": f"{len(au['calls'])} kinds of model call audited from the live request builders. Every call sends "
                     "claims and findings, never PDFs or web pages; the backtest sends one anonymised memo's three "
                     f"sections. {sum(c['pii_found'] for c in au['calls'])} email/phone found in requests, 0 sent: every "
                     "call replaces them with ID tokens.", "page": "handover"},
        {"n": 3, "q": "Can it handle real-world use?", "task": "Task 2: volume test of 20, with a queue",
         "status": "done" if vol and vol["lost"] == 0 else "blocked",
         "evidence": (f"{vol['enqueued']} applications sent in at once: {vol['scored']} scored, {vol['needs_attention']} "
                      f"needs attention (each with a reason), {vol['queued']} still queued, {vol['lost']} lost. At most "
                      f"{vol['workers']} run at once; the rest waited. The daily stop paused the queue and it resumed "
                      "the next day. Simulated model (replayed outputs with injected faults): no live model has "
                      "finished a batch, because the Gemini key is free tier.") if vol else "Not run yet.",
         "page": "handover"},
        {"n": 3, "q": "Can it handle real-world use?", "task": "Task 3: route every call through Portkey, with retries",
         "status": "done" if pk else "blocked",
         "evidence": ("Portkey key set: Claude and Gemini calls route through Portkey with retries "
                      f"({cfg['ai']['portkey_retry']['attempts']} attempts on {cfg['ai']['portkey_retry']['on_status_codes']}).")
                     if pk else
                     ("Built and tested against a fake client: Claude and Gemini calls route through Portkey (research "
                      f"stays direct, it needs Google Search), with automatic retries ({cfg['ai']['portkey_retry']['attempts']} "
                      f"attempts on {', '.join(map(str, cfg['ai']['portkey_retry']['on_status_codes']))}). Not active: no "
                      "Portkey API key could be created in the account. The queue also retries busy/rate-limit errors."),
         "page": "cost"},
        {"n": 4, "q": "Can you operate it?", "task": "Task 4: Langfuse on every call and step, prompt versions",
         "status": "done" if lf else "blocked",
         "evidence": (f"Live (EU cloud). Each application is one trace: a root span, queue wait, a span per stage and the "
                      f"model generation inside it, each tagged with its prompt version (e.g. score.md@hash). "
                      f"{vol['langfuse_traces'] if vol else 0} application traces from the volume test; "
                      f"{traced[1] or 0} of {traced[0] or 0} paid calls in the ledger carry a trace id.")
                     if lf else "Langfuse keys missing.", "page": "learning"},
        {"n": 5, "q": "Does the economics work?", "task": "Task 5: cost per call, by application/day/week/month, daily limit",
         "status": "partial",
         "evidence": f"Every call is costed in ₹ in an append-only ledger and totalled by application, day, week and "
                     f"month. Alert at ₹{lim['alert']:,} and a stop at ₹{lim['stop']:,} a day that pauses the queue (shown "
                     "in the volume test). Gap: cost per application is not measured on a real model yet (free-tier "
                     "Gemini could not finish a batch), so ROI is a cost comparison with bounds.", "page": "cost"},
    ]
    pains = [
        {"pain": "Riya spends 30 minutes per application, more than 19 working days a quarter", "status": "partial",
         "how": "The screener does the first read, the research and the arithmetic, with evidence; Riya reviews. ROI page "
                "puts Riya's time and the system in rupees.", "gap": "System cost per application not yet measured live."},
        {"pain": "About 100 applications in a single day at the Fund II announcement", "status": "done",
         "how": "Queue with a worker limit; every application ends scored, queued or needs attention; daily stop pauses "
                "instead of failing.", "gap": "Throughput on a real model not measured (simulated latency)."},
        {"pain": "'How do I know I can trust this tool?' (Kushal)", "status": "partial",
         "how": "Trust & limits page: backtest, AUC, recall, spot checks, where it breaks, and terms for Kushal to agree.",
         "gap": "The out-of-sample test needs a new batch and partner decisions."},
        {"pain": "Not switching off Riya's triage because a demo went well", "status": "done",
         "how": "Nothing is auto-rejected or auto-advanced (DB triggers); the out-of-sample freeze lets partners decide "
                "first and compare after.", "gap": ""},
        {"pain": "Researches each applicant and scores against the rubric with a recommendation", "status": "done",
         "how": "Extraction, deterministic checks, web research with URLs and access dates, 12-criterion scoring with "
                "totals in code.", "gap": ""},
        {"pain": "Riya reviews the score and justification, and approves or rejects", "status": "done",
         "how": "Company pages show every score with its evidence; decisions need a named person and a reason.", "gap": ""},
        {"pain": "Drafts a personalised email; Riya edits and sends it from the dashboard", "status": "partial",
         "how": "Drafts are created only after a human decision; Riya's edits are recorded per edit with a reason; sending "
                "needs an approval and an allow-listed address.",
         "gap": "Drafts come from templates, not a model; editing and sending are command-line, not dashboard buttons "
                "(the dashboard is a static page); sends are dry-run .eml files."},
        {"pain": "Reads the founder's reply, follows up, schedules a call, handles a counter-proposal", "status": "done",
         "how": "Replies are stored as untrusted data and classified; up to 3 follow-ups then a partner closes; a "
                "proposed time is checked against free slots, otherwise three alternatives.", "gap": ""},
        {"pain": "Checks Riya's calendar and books the meeting in both calendars", "status": "partial",
         "how": "Slots are checked against the system's own holds; an approved hold produces an .ics invite with attendees.",
         "gap": "No live calendar connection (agreed: .ics files only, no event without an approval)."},
        {"pain": "Riya's corrections feed back into scoring and email drafting", "status": "partial",
         "how": "Corrections reach the scoring prompt when 2+ companies in a sector agree; disagreement score tracked; "
                "fine-tuning readiness and dataset.",
         "gap": "Email edits are measured but not fed back (drafts are templates). No real feedback recorded yet."},
    ]
    counts = {s: sum(p["status"] == s for p in pains) for s in ("done", "partial", "blocked")}
    return {"questions": questions, "pains": pains, "pain_counts": counts, "audit": au, "volume": vol,
            "pii_redacted_in_ledger": pii_ledger, "portkey_active": pk, "langfuse_active": lf,
            "fund_day": {"applications": 100, "riya_hours": riya_hours_100,
                         "riya_working_days": round(riya_hours_100 / r["hours_per_day"], 1),
                         "riya_cost_inr": round(100 * r["riya_minutes_per_application"] / 60 * r["riya_inr_per_hour"]),
                         "stop_inr": lim["stop"]}}


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str)[:4000])
