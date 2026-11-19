# Stage 5 run report: blind backtest against the 12 deal memos

Date: 2026-11-19. Commands: `python -m aic.backtest vault|score|unvault|unseal`. Tests: 289 passed.
Per-memo scores: `data/backtest/scores/`; analysis: `data/backtest/result.json` (gitignored).

## How blindness was enforced

1. **Blind copies:** the scorer saw only `data/memos/blind/MEMO-A…L`. Removed: decision, stage (it perfectly predicts the decision in this pack), source, the "Why we…" rationale, names, founding years, places, and one hindsight phrase. IDs are shuffled (memo numbers alternate invested/passed).
2. **Vault:** before scoring, code moved every outcome-bearing file out of the repo:
   - the sealed decisions, the seed PDFs, the memo curation and the notes;
   - your draft rubric (its section 8 lists outcomes) and the prior scores;
   - all Stage 1–4 data and the reports.

   `data/research/_fund.json` was added after I noticed it lists SuperK, Wint, Giva and Jai Kisan as portfolio companies. A repo-wide scan for memo company names then found only code identifiers.
3. **Fresh agent:** it had none of this session's context and was told to read only the scoring prompt, config and blind memos.
4. **Manifest gate:** code computed all 12 scores and hashed every raw and computed score file before `unseal()` would read the decisions. It refuses if any score is missing or changed (tested).
5. **No tuning:** no weight, threshold or rule was changed after unsealing.

## Result

**Band agreement: 6 of 12 (50%). Every memo scored Pass (11–35).** The rubric agrees on all 6 passes and disagrees on all 6 investments. That is exactly the result of "always pass", so **the bands carry no information on this data.**

| Memo | Decision | Total | Founder / 35 | Path / 35 | Band | Result |
|---|---|---|---|---|---|---|
| 1 ePlane | Invested | 19 | 14 | 1 | Pass | disagree |
| 2 Petalry | Passed | 24 | 11 | 9 | Pass | agree |
| 3 Unbox Robotics | Invested | 33 | 23 | 3 | Pass | disagree |
| 4 HopBox | Passed | 24 | 12 | 7 | Pass | agree |
| 5 Wint Wealth | Invested | 21 | 12 | 6 | Pass | disagree |
| 6 CampusCredit | Passed | 11 | 7 | 0 | Pass | agree |
| 7 Giva | Invested | 35 | 20 | 6 | Pass | disagree |
| 8 AeroDrop | Passed | 13 | 10 | 1 | Pass | agree |
| 9 SuperK | Invested | 32 | 20 | 6 | Pass | disagree |
| 10 Coinlane | Passed | 19 | 10 | 6 | Pass | agree |
| 11 Jai Kisan | Invested | 27 | 13 | 9 | Pass | disagree |
| 12 Prepnest | Passed | 17 | 10 | 3 | Pass | agree |

**Agreement by band:** Call 0/0, Partner review 0/0, Pass 6 of 12 (6 invested, 6 passed).

**Ranking does carry signal.** AUC is the chance that a random invested memo outscores a random passed one (0.5 is chance):

| Measure | AUC |
|---|---|
| Total | 0.88 |
| Total, unknowns excluded and re-weighted | 0.92 |
| **Founder subtotal** | **0.99** |
| Path subtotal | 0.56 |
| F2 "owns the hardest risk" | 1.00 |
| F3 candour | 0.89 |
| F1 earned depth | 0.79 |

**Deciding-criteria check.** For each criterion the memo says decided it, did the scorer's reading point the same way (≥ 3 for invested, ≤ 2 or a flag for passed)?
- **Passed: 14 of 14 match.** The rubric finds exactly the reasons the fund passed, including the HopBox capital gate (G2b), the CampusCredit credit-owner gate (G5) and the Coinlane regulatory gate (G2a).
- **Invested: 3 of 15 match.** These are Unbox F3, Giva F2 and SuperK F1.

**Sensitivities (diagnostics, not rubric changes):**
- Excluding unknown criteria and re-weighting the rest gives a top score of 53.8 (Giva). Every memo still lands in Pass.
- Excluding M3 (whose "observed pattern" wording comes from these memos) changes nothing.

## Why the rubric disagrees, and who looks wrong

There are three causes, and they overlap.

- **A. Missing = 0 meets narrative memos.** Memos record no unit economics, market sizing or deck-vs-form numbers. T2 is 0 for all 12; S2 is unknown for all 12; M1 is unknown for 11. That removes up to 35 points before the founders are considered. **The 70-point Call band is unreachable for this kind of record.** I warned of this at Stage 0.
- **B. The redaction removed the evidence for investing.** 12 of the 15 invested deciding quotes live only in the "Why we invested" section, which had to go to keep the scorer blind. The passed memos record their reasons in the founder and risk sections, so they survive redaction. The backtest is therefore structurally harder on investments.
- **C. The pedigree cap hits earned depth.** With your default ("applies to all of F1"), F1 dropped to 2 on 6 memos whenever F2 and F3 were ≤ 2. That includes ePlane (4→2) and Wint (3→2), where F1 measures years spent on the problem, not school or brand names.

| Memo | My verdict | Reasoning |
|---|---|---|
| 1 ePlane (invested) | **Rubric** | The memo says "we were not underwriting the market size". This is a pre-revenue deeptech bet on founders. The rubric needs data that can't exist yet (path 1/35). The pedigree cap removed real depth. The memo's strongest founder evidence, the answer to "what would make you quit?", was redacted (B). |
| 3 Unbox (invested) | **Rubric + redaction** | Founder signals were read correctly (F3 = 4, founder 23/35). "Product already in live sites" was only in the rationale, so the blind text read as pilots (T1 = 1). The total is low only because of missing data (A). |
| 5 Wint (invested) | **Rubric** | The deciding factor was founder–market fit shown by doing unscalable things with customers. F1's anchor ("years of direct experience") and F2's ("owns survival function") don't reward this well, and the pedigree cap lowered F1 further. |
| 7 Giva (invested) | **Rubric, and the memo's record** | The memo invested because the founder knew CAC by channel, return rate and repeat share, but it does not record the numbers. Under "disclosed figures only", T2 = 0. The rubric's rule is right for applications; the memo as a record is incomplete. F2 = 4 matched. |
| 9 SuperK (invested) | **Rubric** | Field behaviour decided it, and F1 = 3 matched. The memo itself notes thin same-store data, so path scored low. The total is held down by A. |
| 11 Jai Kisan (invested) | **Memo, contested** | The blind text includes "credit-risk depth would need to be built or hired quickly", so a low F2 is a fair reading. The memo's deciding line ("Here they did") came from discussion that is not in the founder or risk sections. Aditya was sceptical in meeting 2 ("rural credit is a graveyard"). This is the most defensible disagreement on the rubric's side. |

**The 6 agreements are real at criterion level** (14 of 14 reasons matched) **but trivial at band level**, because everything passed.

## What this does and does not show

- **The rubric, as calibrated, would not have recommended a call for any of the fund's 6 investments.** Its bands cannot be trusted to surface the deals the partners actually make. Its reasons for passing do match the partners'.
- **Founder criteria carry the signal** (AUC 0.99) and path criteria don't (0.56), on this record. That matches the memos' own words ("the person is a primary variable").
- **These numbers are in-sample and optimistic.** The rubric's anchors quote these same memos (e.g. "the NBFC handles that", "solved once the tech works"), and M3's "observed pattern" is distilled from the invested memos. F2 = 1.00 is partly the rubric recognising its own source text. Only new decisions, or the uneasy passes such as Ledgerly (not in the pack), can test it out of sample.
- **Twelve memos are too few** to set a threshold. Any threshold that splits these 12 would be fitting to them, so I have not proposed one.

## Assumed

1. "Agree" means Call ↔ invested and Pass/Hold ↔ passed; Partner review would count as no commitment, though none occurred.
2. The deciding-criteria mapping in the sealed file was written by me from each memo's own rationale. It is the comparison key, not a score.
3. One scorer run. Scorer-to-scorer variance is not measured.

## Decisions for you (I have changed nothing)

Each option below would change the rubric. Any of them chosen *because* of this backtest is fitting to the seed data and should be labelled as such:

1. **Pre-revenue / narrative evidence.** Keep "missing = 0" everywhere, or score path criteria as "not applicable" (excluded and re-weighted) for pre-revenue deeptech? Even the excluded-and-re-weighted view tops out at 53.8 here, so this alone would not create Calls.
2. **Pedigree cap scope.** Your default applies the cap to all of F1. Limit it to F1 evidence that is credentials only (the rubric's original intent, "pedigree alone cannot carry the founder score")? This would restore ePlane, Wint and others on F1.
3. **Use founder and path subtotals as the primary output** for partner review, with the total secondary, given founder AUC 0.99 vs total 0.88 (in-sample)?
4. **Out-of-sample test.** Provide the original applications (decks and forms) for some memo companies, or the Ledgerly and uneasy-pass notes. That is the only evidence that would show whether the rubric works on the material it will actually see.
