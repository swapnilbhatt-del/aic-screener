# Feedback loop and fine-tuning (lecture, 24 Nov)

Date: 2026-11-24. This compares the lecture with what was built and records what was added. Decisions marked "user" are yours from 2026-11-24.

## What the lecture asks for, and where it now is

| Lecture item | Before | Now |
|---|---|---|
| Signal: the gap between the system's recommendation and what Riya approves and sends | Corrections and decisions stored. Riya's email edits overwrote the draft, so that gap was lost | Three separate signals (`aic/learning.py`): **band** (model band vs the partner's decision), **criteria** (share of scored criteria corrected), **email** (how much Riya changed the draft, 0 to 1). None is blended into one number |
| Feedback stored, indexed and tagged with context | `corrections`: company, sector, criterion, scores, reason, who, when. Append-only | Plus `scope` on corrections, `email_edits` (every edit with before, after, reason, scope and who), and `feedback_flags`. All append-only, and human-only by DB trigger |
| Past feedback retrieved and injected into the prompt | Shown on the company page only | `feedback.lessons()` goes into the scoring request as `past_feedback`. It carries every reason and an instruction to apply a lesson only where the same reasoning holds |
| Disagreement score over time; it falls, then plateaus | None | Monthly and by-sector rates for each signal. A plateau check covers the last 3 months (config `learning`) |
| Spikes: new categories, thesis drift, new contact types | None | The page lists sectors with no usable feedback ("expect higher disagreement"). Thesis drift appears as a rise in the monthly rate |

## The lecture's limits, and the guard for each

| Limit | Guard |
|---|---|
| The system doesn't capture the "why" | Every correction and email edit needs a one-line reason, enforced in code and by the DB. The reason travels into the prompt with the lesson |
| Six edits stored as one; an exception gets misapplied (the Rahul referral) | Each email edit is its own row with its own reason. An edit marked `this_case` (for example a referral mention) is logged and counted, but never reused |
| Numbers without context | An email edit keeps the full before and after text. A lesson carries the companies and reasons it came from, so the model sees which number and why |
| Founder fit is subjective | Founder criteria stay human-correctable, with reasons. A lesson needs 2+ companies to agree (below), so one surface rule doesn't spread |
| Bad days | A named person can flag any correction or edit as `bad_day` or `retracted`. Flagged feedback is excluded from lessons, signals and the dataset |
| The 80/20 constraint | The base prompt stays fixed. Each run reports `feedback_share_of_prompt` and `lessons_injected` |

**Injection rule (user: only when 2+ agree).** A lesson reaches the scoring prompt only when all of these hold:
- corrections on at least 2 other companies agree;
- they're in the same sector, on the same criterion, in the same direction;
- each is scope `general` and not flagged.

At most 5 lessons, newest first (config `feedback.inject_min_agreeing_companies`, `inject_max_lessons`).

## Fine-tuning (user: readiness check and dataset; the bar is a proposal for Kushal)

- **Readiness** (`python -m aic.learning readiness`, and the dashboard's "Feedback & fine-tuning" page). The proposed bar, in `finetune.bar`:
  - disagreement plateaued above 30% for 3 months;
  - at least 200 labelled pairs;
  - the same mistake on 5+ companies.

  A person also confirms the easy fixes were tried first (rubric descriptions, data sources, a stronger model) and that the rule is stable. Nothing trains automatically.
- **Dataset** (`python -m aic.learning export` writes to `data/finetune/`, which is gitignored because it holds founder data):
  - chat-format pairs built with the same prompts as the live app;
  - scoring pairs carry the human corrections and their reasons;
  - email pairs map the system draft to what Riya approved (unedited approvals count as agreement);
  - deduplicated, no sector above 40% (a proposal), split 75/15/10 by sector with a stable hash;
  - the test split is held out.
- **Route:** self-managed (Unsloth or Colab) on a small Gemma, Qwen or Llama, so founder data stays in-house. Serving needs its own GPU endpoint; Vercel can't host it.

## What's not measured yet

There is no feedback yet: 0 corrections, 0 partner decisions and 0 approved emails. Every rate is shown as "—", not as zero. The readiness check says "not yet", and the dataset is empty. Per the lecture, fine-tuning before launch needs historical data that the case doesn't provide, so this waits for about 3 months of live feedback.

Emails are drafted from templates, not by a model. So the email signal measures how much Riya changes the template drafts, and no email lessons go into a prompt.
