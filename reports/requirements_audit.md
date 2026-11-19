# Requirements audit

Date: 2026-11-19. Every requirement in (A) the build brief given at the start of the project and (B) the case
brief `MESA_T2_Case 03_All in Capital.pdf`, with where it is met. Tests: 376 passed.

Status: **Met** = built and tested. **Partly** = built, with a limit stated. **By design** = deliberately limited by a hard constraint.

## A. Build brief

### Hard constraints

| # | Requirement | Status | Where |
|---|---|---|---|
| 1 | No email or calendar event without an approval recorded in the DB, enforced in code | Met | `aic/db.py` triggers; `tests/test_approval_gate.py`, `tests/test_outreach.py` (send without approval fails, writes nothing) |
| 2 | Nobody auto-rejected or auto-advanced; every outcome to a human gate | Met | `outcomes` table: created undecided, a decision needs a named human and a reason (DB trigger); drafting needs a human decision |
| 3 | Missing data scores 0 and is marked unknown, never skipped or imputed | Met | `aic/scoring.py` validation (unknown ⇒ 0); T2 sub-parts; UNCHECKABLE checks; `tests/test_scoring.py` |
| 4 | Every score cites a quote or figure, its location, and URL + access date for external claims | Met | evidence refs resolved in code; `test_every_score_cites_evidence` |
| 5 | Founder replies are untrusted; never act on instructions in them | Met | replies stored immutable, labelled by fixed rules; instruction-like text → unclear; action depends on label only; injection test |
| 6 | Only placeholder addresses in test mode; never deck addresses | Met | deck addresses and company domains refused; allow-list (empty) enforced by DB at send |
| 7 | Pedigree cannot raise a founder score above 2 unless another founder criterion ≥ 3 | Met | `pedigree_cap` in config, applied in code; tests. (Backtest shows it also lowers earned depth: see Stage 5.) |

### Stages

| Stage | Requirement | Status | Where |
|---|---|---|---|
| 0 | Git init, `.gitignore` for seed, CLAUDE.md with constraints, one config for weights and thresholds (70/55) | Met | `CLAUDE.md`, `config/rubric.yaml`, `aic/config.py` |
| 1 | Applications parsed into structured records with source page for every field | Met | `aic/forms.py`, `aic/claims.py`, `aic/ingest.py`; 944 claims, 0 invalid |
| 1 | Memos and notes parsed into decision records (decision, deciding criteria, reasons) | Met | `aic/memos.py` (sealed decisions with verified quotes), `aic/notes.py` |
| 2 | Recompute every market-size formula and unit-economics figure; stated vs recomputed; pass/fail | Met | `aic/checks.py`, 143 checks |
| 2 | Cross-document checks: customers, revenue, team, credentials, raise | Met | `cross_documents()`, `credentials()` |
| 2 | Reuse and verify the reference script | Met | `aic/reference_reconcile.py`: 34/34 agree |
| 3 | Research market size and trend, competitors (incl. funded), founder background, regulatory dependency | Met | `data/research/*.json`, 198 findings; founders: none found online (stated) |
| 3 | URL, date and claim for every finding; conflicting sources marked; cached | Met | `aic/research.py` validator; 25 conflicts; hashes in `stage3_cache_manifest.json` |
| 4 | Score rubric criteria 0–5 with evidence; totals in code; founder and path subtotals | Met | `aic/scoring.py` |
| 4 | Close call within 5 points; integrity cap at partner review | Met | config + code; tests incl. mutation |
| 5 | Score 12 memos blind; decisions in a separate file read only after all scores | Met | `aic/backtest.py`: vault, hash manifest, `unseal()` refuses otherwise; tests |
| 5 | Agreement by band, every disagreement with reasoning, rubric or memo wrong | Met | `reports/stage5.md` |
| 5 | No tuning without flagging overfitting | Met | nothing tuned; options listed and flagged |
| 6 | Corrections log (company, criterion, model, human, reason, date) | Met | `aic/feedback.py`, DB table (human-only, append-only) |
| 6 | Surface past corrections for same sector and criterion | Met | `past_corrections` on each score card |
| 6 | Never change weights automatically; propose after 3+ similar corrections as a diff | Met | `weight_proposals`; test proves config untouched |
| 7 | Draft emails; reply classification with human confirmation for no/unclear | Met | `aic/outreach.py`; DB trigger on no/unclear |
| 7 | Tue/Thu afternoon 30-minute slots; tentative holds; day-3 follow-up, max 2 | Met | slots from next business day; `.ics` holds after approval; follow-up rules + DB cap |
| 7 | Every send needs an approval record; dry-run by default | Met / By design | only a dry-run sender exists; no live sending |

### Output requirements and working rules

| Requirement | Status | Where |
|---|---|---|
| Dashboard: score card, gate status, evidence links, discrepancies, recommendation, decision history | Met | local `dashboard/index.html`; public https://aic-screener.vercel.app; artifact (private) |
| Run report per stage with counts, failures and open questions | Met | `reports/stage0.md` to `stage7.md` |
| Tests for every deterministic check and the approval gate | Met | 359 tests |
| Ask before judgement calls that change the rubric | Met | every rubric decision recorded with date in `config/rubric.yaml` |
| Say when a source is missing or contradictory | Met | not-found log, conflicts, UNCHECKABLE checks, "What's missing" page |
| Commit after each stage; checkpoint lists verified / assumed / to decide | Met | git history; each stage report |

## B. Case brief (All In Capital)

| Requirement (Kushal's words, paraphrased) | Status | Where |
|---|---|---|
| Take a week of intake, the whole pile, and return a read on each | Met | all 10 applications in one batch |
| Score against the thesis criterion by criterion, with the source behind every claim | Met | score cards with cited evidence |
| Say what it couldn't find out | Met | unknown criteria, not-found log, "What's missing" page |
| Say whether to take the call; make the case, don't decide | Met | band + reasons + routing; outcomes stay undecided |
| Don't score "7/10" without saying which part of the thesis | Met | 12 criteria with weights, subtotals and M3's two thesis fields |
| Go and find what isn't in the deck | Met | Stage 3 research; G1 from the public portfolio |
| A correction should count next time on a similar company | Met | Stage 6 reuse and proposals |
| No email and calendar busywork after a yes; Kushal sees every outcome first | Partly / By design | drafts, slots, holds and follow-ups are generated; sending and booking stay dry-run behind approvals (hard constraint 1). No live mailbox or calendar is connected |
| Run against past decisions; how often it disagrees; who was wrong | Met | Stage 5: 6/12, all scored Pass; per-memo verdicts |
| Reconstruct the thesis from public sources; say what absence costs | Met | `_fund.json` thesis and portfolio; "What's missing" page and `trust_and_limits.md` |
| Reconcile Riya's drift between stated thesis and practice | Partly | shown as two fields (public line vs observed pattern) on M3; reconciling them is a partner decision |
| Stop the nineteen days a quarter | Partly | measured: about 17 minutes per batch of 10 vs 5 hours; partner review time not yet measured ("Time & cost" page) |
| Promising applications already have a call on the calendar | By design | tentative holds as `.ics` after approval; no live calendar |
| Kushal knows, in writing, in numbers, agreed in advance, how far to trust it and where it breaks | Met (pending sign-off) | "Trust & limits" page and `reports/trust_and_limits.md`, with proposed terms and a sign-off line |

## Open items

1. **Out-of-sample test:** harness built (`aic/oos.py`, `reports/oos_harness.md`): freeze, blind, decide, evaluate once against the proposed bar. Needs the next batch of applications and partner decisions to run; the Stage 5 backtest remains in-sample until then.
2. **Sign-off:** Kushal to agree the trust terms (or set his own bar).
3. **Partner review time:** time it on the first real batch to finish the 19-days comparison.
4. **Live sending and booking:** a mailbox and calendar connection is out of scope while hard constraint 1 and dry-run apply. A change would need your explicit decision.
