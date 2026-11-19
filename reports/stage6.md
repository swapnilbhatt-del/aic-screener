# Stage 6 run report: feedback loop

Date: 2026-11-19. Tests: 310 passed. The real corrections log is **empty**: only you or the partners can add to it.

## What was built

| Piece | How it works | Enforced by |
|---|---|---|
| Corrections log | `python -m aic.feedback add <Company> <Criterion> <human score> "<reason>" <your name>`. Records company, sector, criterion, **model score read from the score card** (so it can't be misquoted), human score, one-line reason, who and when. | DB triggers reject: a model/system/auto/claude author, an unchanged score, a multi-line reason, and any update or delete (append-only). Code rejects: unknown criterion, score outside 0–5, reason over 200 characters. |
| Reuse | Every score card now carries `past_corrections`: corrections on **other** companies in the **same sector**, by criterion, phrased as "Last time on a similar company (X, sector) [name] moved F2 from 3 to 1 because …" (the wording asked for in the notes). Also `python -m aic.feedback surface <Company>`. | Tested: same sector only, own company excluded. |
| Proposals | `python -m aic.feedback propose` looks for **3 or more corrections on the same criterion, in the same direction, across 3 or more distinct companies** (config `feedback.min_similar_corrections: 3`). For each group it records a **proposal**: a unified diff of `config/rubric.yaml` plus a note that the anchor may be the real problem. | Stored as `proposed` in `weight_proposals`. Accepting or rejecting needs a named human (DB trigger). **No code path writes the config** (tested by hashing the config before and after, and by scanning the source). |

### How a candidate diff is built (mechanical, for discussion only)

- The corrected criterion moves by up to 5 weight points in the corrections' direction.
- The offset comes from the largest other criterion in the same group, which keeps the founder/path/thesis/structure subtotals and the total of 100.
- If a 5-point move would take a weight to zero, the step shrinks to 2, then 1.
- If no valid move exists, the proposal is still recorded with "discuss the anchor instead", so a qualifying group always reaches a human.
- Every candidate is checked against the config rules before it is stored.

## Synthetic demo (in-memory DB, real score cards, reasons marked SYNTHETIC)

Three made-up corrections raised M2 from 1 to 2 for CAPilot, RentRoute and Settlr (all fintech).

- **EarnWise's card would show:** "Last time on a similar company (CAPilot, fintech) Demo Reviewer moved M2 from 1 to 2 because SYNTHETIC: reason to win under-credited" (and the other two).
- **Proposal produced:** M2 10 → 12, M1 5 → 3. The 5-point step would have zeroed M1, so it shrank to 2. Shown as a diff, status `proposed`. Nothing was applied.

## Verified

- **Author, score and append-only rules (DB):** non-human authors, unchanged scores and multi-line reasons are rejected; edits and deletes are blocked.
- **Surfacing:** same sector, other companies only.
- **When proposals fire:** fewer than 3 corrections, mixed directions, and the same company corrected 3 times all produce no proposal.
- **Proposal output:**
  - a proposal is a valid diff and is not proposed twice;
  - the shrinking step works;
  - a group with no valid move still produces a proposal;
  - deciding a proposal needs a named human;
  - the config file is byte-identical after proposing.

## Assumed

1. **Sector for similarity** is the form's selected sector, folded to the public list (fintech, deeptech, consumer tech, consumer brands); anything else is kept as written, e.g. "other (healthcare)". Talkbook selected "Consumer tech" although it is B2B SaaS, so it would match consumer-tech corrections.
2. **"Similar"** means same criterion and same direction across distinct companies, regardless of sector. Surfacing on cards uses the stricter same-sector rule.
3. **The candidate-diff mechanics are my design** (offset in group, shrinking step). They only shape what you are shown; a person edits the config.

## For you

- Corrections are the input this loop needs. After the partners review the Stage 4 cards, each change should be entered with a one-line reason so it can be reused.
- If you'd rather "similar" meant same sector **and** criterion for proposals too, that is a one-line config change. I've left it as the brief describes.
