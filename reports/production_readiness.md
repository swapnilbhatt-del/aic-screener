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

## Update 2026-11-21: Gemini

You asked to run on your Gemini key. `ai.models` now uses `gemini-4-carbon`, which Google's model page calls its "most capable reasoning model". Prices come from Google's pricing page, accessed 2026-11-21: $2 input, $10 output (thinking included), $0.10 cached input per 1M tokens, and search grounding at $14 per 1,000 searches.
- **Price change:** Carbon's price doubles on 2026-12-01. Edit the price line then, or the ledger will undercount.
- **Model status:** Carbon has no "Stable" badge. The stable alternative is `gemini-3.8-flash`.
- **Research:** uses Google Search grounding instead of Anthropic web search. Each output file keeps the queries and sources Google returned (`grounding`) next to the model's own citations, so a reviewer can check them. Grounding sources may be Google redirect links rather than the publisher's URL. The validator still requires an http(s) URL on every finding.
- **Portkey:** routes Claude calls only, for now. Gemini calls go direct. Wiring Gemini through Portkey's OpenAI-compatible endpoint would lose Google Search grounding, so it waits until there is a Portkey account to test against.
- **Accounts:** both key APIs you pointed to need an existing account.
  - Portkey's `POST /v1/api-keys/{type}/{sub-type}` is authenticated with an existing `x-portkey-api-key`.
  - Langfuse's organizations API is "only available on self-hosted instances, not on Langfuse Cloud" and needs an admin key.
  - So the first key for each has to come from a sign-up you do yourself.

## First metered run, 2026-11-21 (Gemini, free tier)

The key you gave me is on Google's free tier:
- **`gemini-4-carbon`:** quota 0 on the free tier, so it can't run on this key.
- **`gemini-3.8-flash`:** 503 "high demand".
- **`gemini-3.5-flash-lite`:** works for small calls. `ai.models` now uses it.
- **Google Search grounding:** 429 on every call, while plain calls on the same key succeed. Research can't run on this key.
- **Scoring for CAPilot, and extraction for CareCorner:** 503 "high demand" after 4 retries over about 7.5 minutes. I stopped the batch there.

Measured so far:
- **One extraction (CAPilot):** 2,520 input and 3,748 output tokens (thinking included), ₹0.89 at paid-tier prices. That's ₹0 billed on the free tier.
- **Claim count:** 35 claims, against 76 from the build-session (Claude) run. Not reviewed yet; that's `compare`'s job.

Not measured: research, scoring, and a per-application cost. What it needs: billing enabled on the Gemini key (paid tier: search grounding, Carbon and higher priority), or a retry when Google is less busy.

Retry, 2026-11-24 (free tier, as you chose):
- **Small test call:** worked.
- **Google Search:** still refused with 429.
- **CAPilot scoring:** 503 "high demand" after 4 retries.
- **CareCorner extraction:** 503 "high demand" after 4 retries.

Stopped again. On this key, the free tier can't complete the batch.

Third attempt, 2026-11-24 (you asked to use the Gemini key). I tested what triggers the 503s:
- **CAPilot scoring:** 503 on `gemini-3.8-flash` and on `gemini-3.5-flash-lite`.
- **Same request with other settings:** 503 at thinking high, medium and low, and at output caps of 32k and 16k.
- **Request size:** 15k and 30k characters passed, 60k failed. Scoring requests are 98k–139k characters (the fund-wide research block alone is 47k).
- **CareCorner extraction (4.4k characters):** 503 at output caps of 32k, 16k and 8k, at low thinking, with no thinking setting, and with a one-line system prompt.
- **A one-line call, three times:** two OK, one 503.

The 503s are capacity on Google's free tier, not anything in our requests. Larger calls fail more often, and it doesn't clear with retries over 7.5 minutes. No new stage completed.

## Update 2026-11-24: Gemini through Portkey

- **Gemini calls now go through Portkey once `PORTKEY_API_KEY` is set.** They use Portkey's OpenAI-compatible `/v1/chat/completions` with `x-portkey-provider: google`, authenticated with your Gemini key, or a Portkey virtual key if you set one. Research still goes direct, because Portkey's OpenAI route doesn't carry Google Search grounding. The ledger's `gateway` column records which route each call took.
- **Langfuse traces every call**, on any route, once its two keys are set.
- **`python -m aic.llm check`** sends one tiny metered call and prints the route and the Langfuse trace id.
- **Not verified yet:** this is tested against fake clients only. No Portkey or Langfuse key exists yet; both need accounts you create.
- **No thinking setting via Portkey:** Gemini calls through Portkey don't send the thinking level (`effort`), because the documented way to pass it was unclear. Direct calls still send it.

## Update 2026-11-24: Langfuse is live

- **Keys:** your Langfuse keys are in `.env` (gitignored). They work on the EU region (`cloud.langfuse.com`, project "My Project").
- **Endpoint change:** the old `/api/public/ingestion` endpoint now answers **410 Gone**. Tracing now uses the OpenTelemetry endpoint `/api/public/otel/v1/traces` with `x-langfuse-ingestion-version: 4`, one generation span per call.
- **Verified live:** `python -m aic.llm check` sent one call, and the trace was read back through the v2 Observations API with the right model (`gemini-3.5-flash-lite`), tokens (15 in, 5 out) and cost ($0.000017). That cost matches our ledger. Langfuse's own price for the model also matches our config.
- **Portkey is still not active.** Its key-creation API (`POST /v1/api-keys/{type}/{sub-type}`) itself needs an existing Portkey API key, so the first key has to come from the Portkey dashboard (API Keys → Create).
