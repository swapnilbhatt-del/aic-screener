# Ready to hand over? (Case 04, Build 5)

Date: 2026-11-25. This is Kushal's question, *"Can I hand this to Riya as her main way of screening before the announcement? How do I know I can trust this tool?"*, answered task by task. The dashboard page **Ready to hand over?** (`#handover`) shows the same with charts.

| Question | Task | Status | Evidence |
|---|---|---|---|
| 1 Does it work? | Evals | Done, with limits | Blind backtest on 12 memos. Checks agree 34/34 with the reference script, and claim recall is 40/40. Every memo scored Pass, so band agreement equals "always pass". The out-of-sample test hasn't run |
| 2 Is it safe? | Task 1: audit prompts | Done | See below: every call is audited from the live request builders. Emails and phone numbers are replaced with ID tokens on every call |
| 3 Real-world use? | Task 2: volume test of 20, with a queue | Done (simulated model) | 20 in, 15 scored, 5 needs attention with a reason, 0 lost. A pause, then a resume |
| | Task 3: Portkey with retries | Built, **not active** | Retries are configured (3 attempts on 429/500/502/503/504). No Portkey API key could be created in the account |
| 4 Can you operate it? | Task 4: Langfuse on every call and step, prompt versions | Done, live | One trace per application, with steps and generations nested and each step's prompt version |
| 5 Economics? | Task 5: cost tracking | Done, except a measured cost per application | Totals by application, day, week and month. The daily stop pauses the queue. Cost per application on a real model isn't measured |

## Task 1: prompt audit (`python -m aic.audit`)

These are averages over the 10 applications, measured from the same functions that build the live requests.

| Call | Sends | Available → sent | Emails/phones found → sent |
|---|---|---|---|
| Extraction | Page text only, with page numbers; no layout copies | 13.8k → 9.6k chars (−31%) | 1 → 0 |
| Research | A short research brief; no documents. Findings come back with a URL and access date, never whole pages | 50.5k → 10.3k (−80%) | 0 |
| Scoring (full card) | Validated claims, check results, research findings and the parsed form; no PDFs or pages | 176k → 126k (−29%) | 2 → 0 |
| Scoring (one criterion) | Only that criterion's inputs, from `finetune.criterion_inputs` | 131k → 18k (−86%) | 0 |
| Backtest | One anonymised memo at a time, with its 3 relevant sections only | 42k for all memos → 1k (−98%) | 0 |

**Redaction.** Every model call goes through `llm.redact` before anything is sent. Email addresses and phone numbers become stable ID tokens, for example `[email:1d4c122b]`; the same address always gets the same token. The ledger records how many were replaced on each call (`ai_calls.pii_redacted`). Founder names are kept, because research has to search for them.

**A bug the volume test caught.** The first version scrubbed the encoded JSON text. In `…\nhello@yatrika.example`, it swallowed the `n` of the `\n` escape, which broke the JSON. Yatrika's extraction failed because of it. The fix scrubs the decoded values, and there's a test for it.

## Task 2: queue and volume test (`python -m aic.queue volume-test`)

**How the queue works**
- Every application gets a `jobs` row. The database refuses to delete jobs, and "needs attention" can't be set without a reason.
- At most 4 jobs run at once; the rest wait their turn in order.
- Each job runs extraction, research and scoring through the metered client.
- A transient busy or rate-limit error puts the job back in the queue for another attempt.
- The daily stop pauses the queue: jobs already waiting stay queued, with the reason.

**How the test ran**
- 20 applications at once: the 10 real ones, each sent in twice.
- The model is **simulated**. Each call replays that application's stored output, so the real validators run, and six faults a real batch meets are injected: a one-off 503, a persistent 503, prose instead of JSON, an invalid research file, max tokens, and a refusal. No model was paid.
- Every application has a live Langfuse trace.

**Results**
- **Phase 1** (the daily stop lowered to ₹12): 6 scored, 4 needs attention, and **10 queued**, "paused before scoring".
- **Phase 2** (the limit resets, standing in for the next day): the queue drained. Final count: 15 scored, 5 needs attention, 0 queued, **0 lost**.
- The one-off 503 was retried and scored.
- Each needs-attention case has its own reason, for example "research failed after 2 attempts: 503", "scoring failed: no JSON", or "research output failed validation: missing accessed_date".

**Not measured:** throughput and failure rates on a real model. The free Gemini key refuses search and often answers "busy", so no live batch has finished.

## Task 3: Portkey

Claude calls, and Gemini calls except research (which needs Google Search grounding), go through Portkey once `PORTKEY_API_KEY` is set. Each Portkey call sends `x-portkey-config` with retries switched on (`ai.portkey_retry` in config). It's tested against fake clients only; there's no key yet.

## Task 4: Langfuse

**What one application's run looks like** (read back from Langfuse's API for `Talkbook#1`):

```
SPAN       application Talkbook#1        (root)
SPAN         queue wait
SPAN         extraction                  prompt extract_claims.md@95dbee14
GENERATION     extraction                gemini-3.5-flash-lite, same prompt version
SPAN         research                    prompt research.md@e2d4984a
GENERATION     research
SPAN         scoring                     prompt score.md@c5475792
GENERATION     scoring
```

- **Prompt versions:** each is the prompt file's content hash. It's recorded on the Langfuse step, the generation and the ledger row (`ai_calls.prompt_version`).
- **Endpoint:** the old Langfuse ingestion endpoint returns 410, so tracing uses the OpenTelemetry endpoint.

## Task 5: cost

- **Every call is costed** in rupees in the append-only ledger, totalled by application, day, week and month. The cost page and the hand-over page show these.
- **Limits:** an alert at ₹1,000 a day, and a stop at ₹10,000 that blocks calls and pauses the queue (shown in phase 1). Only a named person can release a manual stop.
- **Fund II day:** 100 applications means 50 hours of Riya's time, about 6.3 working days. At the build-session upper bound (₹73 an application, before output tokens and searches), 100 applications would cost about ₹7,300, under the ₹10,000 stop.

## Pain points from the case still partly open

- **Emails from the dashboard:** drafts come from templates, and Riya edits and sends from the command line, not with dashboard buttons. The dashboard is a static page, and sends are dry-run.
- **Calendars:** there's no live calendar. Invites are `.ics` files only, as agreed, and nothing is created without an approval.
- **Riya's email edits** are measured but not fed back into drafting. No real feedback has been recorded yet.
- **Trust:** the out-of-sample test needs a new batch and partner decisions.
- **Cost per application** on a real model isn't measured.
