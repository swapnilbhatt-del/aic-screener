# Production readiness: cost, ROI and the 19 Nov lecture

Date: 2026-11-20. This compares the lecture ("AI cost tracking and ROI modeling before production", 19 Nov) against
what was built, and records what was added. Decisions marked "user" were made by you on 2026-11-20.

## What the lecture asks for, and where it now is

| Lecture item | Before | Now |
|---|---|---|
| Know your costs: record input/output tokens and cost for every AI call in a DB table | Token totals per agent run only (`run_metrics.json`), no price | `aic/llm.py`: every model call goes through one client and is appended to `ai_calls` (task, company, model, input/output/cache tokens, web searches, cost in USD and ₹, latency, status, trace id). The table cannot be edited or deleted |
| An admin page showing spend | None | Dashboard → **AI cost & ROI**: spend today and to date, by task, model, day and application, plus alerts and stops |
| Alerts and a kill switch (example: alert at ₹1,000/day, stop at ₹10,000/day) | None | `ai.spend_limits_inr_per_day` (user: alert ₹1,000, stop ₹10,000). Crossing the alert records an alert. Crossing the stop blocks every call for the rest of the day. A call whose worst case would cross the stop is refused before it is made. A partner can pull the switch (`python -m aic.llm stop`); only a named human can release it (DB trigger) |
| Same unit for ROI: Riya's time in ₹ | Hours only | `roi.riya_inr_per_hour` (user: ₹1,000/h, a **placeholder**). Riya costs ₹500 per application and ₹1,52,000 a quarter |
| Lever 1, send less | Agents read whole files | Extraction sends page text without the layout copy. Scoring sends validated claims, checks and research, never PDFs |
| Lever 2, cache everything | Research cached as files | Output files act as a cache (nothing is re-bought without `--force`). `llm_cache` serves identical requests at ₹0, and the stable prompt prefix uses prompt caching |
| Lever 3, cap the spend | None | Kill switch above |
| Lever 4, cheaper models where quality holds | One model, implicit | Models are set per task in `ai.models`. `python -m aic.runner compare <stage> <Company> <model_a> <model_b>` reports cost and output differences. A person switches models only on that evidence |
| Portkey (gateway, stress test) | None | All calls route through Portkey when `PORTKEY_API_KEY` is set. **Needs your account** |
| Langfuse (traces, RCA) | None | Each call sends a trace and a generation when the Langfuse keys are set; `ai_calls.trace_id` links the two. **Needs your account** |
| Model calls as API calls (needed for all of the above) | Build-session subagents | `aic/runner.py` runs extraction, research (web search and fetch tools) and scoring as metered API calls, using the same prompts, output files and validators |

## The case flow in the lecture vs the system

| Lecture | System | Note |
|---|---|---|
| Rubric from memos, notes, partner feedback | Stage 0–5 | Hardest step, per the lecture; done and backtested |
| Riya reviews, may research more, decides; feedback loop on disagreements | Human-only decisions; Stage 6 corrections | Unchanged |
| Riya edits the email, then it is sent | Draft → approval → dry-run send | Unchanged (hard constraint 1) |
| Calls on **Mondays and Thursdays** | Tuesdays and Thursdays | **Conflict between the lecture and the build brief.** User decided to keep Tue/Thu |
| Founder proposes another time; check it, confirm or counter | New | The reply is parsed for one clear day and time and checked against our own slots (days, window, lead time, existing holds). If the time is free, one hold is proposed for approval; otherwise three alternatives are offered. The founder's text never decides an action |
| Follow up after no reply, **max 3, then rejected** | Max 2 | User: up to 3. After the last one, the thread goes to `no_reply` and a partner closes it by name. **Never auto-rejected** (hard constraint 2 overrides "rejected") |
| Kushal joins first meetings only for deeptech | New | Holds and `.ics` list attendees: Riya, plus Kushal when the form's sector is Deeptech (Pumpwise) |
| cal.com / live calendar | `.ics` files | Out of scope while dry-run and hard constraint 1 apply |
| Pricing (per seat, per use, outcome) | Not built | Relevant to "build your own product", not to the fund. Once metering gives a per-application cost, it can feed a Cursor-style heavy-user scenario |

## What is not measured yet

- **System cost per application.** The ledger is empty because the 10 applications were scored by build-session agents, which report one token total and no input/output/cache split. Bounds on that total alone: ₹3.7 if every token were a cache read, ₹73 if every token were uncached input, on 2,07,497 tokens per application. That is 0.7%–14.6% of Riya's ₹500, before output tokens and searches. The first metered batch gives the real figure.
- **Quality.** The saving counts only if the output matches Riya's. The backtest agreed on 6 of 12 memos, and the out-of-sample test has not run.
- **USD/INR.** `ai.usd_inr: 88` is a placeholder with no source. Replace it with the rate your card is billed at.

## What you need to do

1. Create a **Portkey** account and a **Langfuse** account yourself. I can't create accounts or handle their passwords. Put the keys in `.env` (copy `.env.example`; `.env` is gitignored), with an Anthropic API key or a Portkey virtual key for Anthropic.
2. First metered run (approved by you on 2026-11-20, to run once the keys are in): `python -m aic.runner batch` runs all three stages for the 10 applications into `data/api_run/`, so the build-session outputs in `data/` are not overwritten. It stops at the kill switch.
3. Replace the two placeholders, Riya's hourly cost and the USD/INR rate.

Not yet verified against live services: the Portkey header set, the Langfuse ingestion payload and the server-side
refusal `fallbacks` parameter through Portkey. These are tested with a fake client only. Check each on the first
real call; the ledger records any error.
