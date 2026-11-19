# Stage 1 run report: ingest

Date: 2026-11-19. Command: `.venv/bin/python -m aic.ingest`. Tests: 132 passed.

## What was built

| Module | Does | How it is checked |
|---|---|---|
| `aic/text.py` | PDF → per-page text (plain and layout), slide labels, whitespace-insensitive quote finder | all 22 PDFs, 127 pages extracted; no empty pages |
| `aic/forms.py` | Deterministic parser for the two-column application form | 10/10 forms, 25–33 fields each, every field has a page; all values re-spaced against plain text |
| `aic/units.py` | INR/count/percent parsing (L, Cr, lakh Cr, K, M) | 34 unit tests |
| `aic/claims.py` | Validates model-extracted claims; computes every number in code | quote must be on the cited page; `as_written` must be inside the quote |
| `prompts/extract_claims.md` | Instructions for the extraction agents | committed so the extraction can be rerun |
| `aic/memos.py` | Memo pack → 12 blind, anonymised memos + one sealed decisions file | leak tests (see below) |
| `aic/notes.py` | Partner notes → 41 bullet records with meeting, topic, page, marker-based type | parse tests |
| `aic/ingest.py` | Assembles `data/applications/<Company>.json` | — |

## Counts

| Company | Form fields | Claims (deck / form) | Invalid |
|---|---|---|---|
| CAPilot | 26 | 76 (40 / 36) | 0 |
| CareCorner | 25 | 86 (47 / 39) | 0 |
| EarnWise | 27 | 65 (29 / 36) | 0 |
| GrainKind | 27 | 119 (68 / 51) | 0 |
| Pumpwise | 26 | 124 (70 / 54) | 0 |
| RentRoute | 26 | 83 (38 / 45) | 0 |
| Settlr | 26 | 93 (49 / 44) | 0 |
| StockSathi | 33 | 125 (67 / 58) | 0 |
| Talkbook | 27 | 103 (57 / 46) | 0 |
| Yatrika | 26 | 70 (32 / 38) | 0 |
| **Total** | 269 | **944** | **0** |

Memos: 12 parsed (6 invested, 6 passed), 29 deciding-criteria quotes all verified against the memo text, 31 redactions. Notes: 41 records across 5 meetings (5 decision, 3 action, 4 score, 29 note).

## Verified

- Every one of the 944 claims has a verbatim quote found on the cited page, and every number was computed by code from the quoted text.
- **Recall check, independent of the extractors:** 40 key figures I read from the PDFs myself (customer counts, MRR, TAM/SAM/SOM, CAC, team size, raise) are all present with the correct value and tag. All 7 market formulas have their multiplied inputs recorded (`tests/test_claims_recall.py`).
- Blind memos contain no decision, stage, source, "Why we…" text, founder name, company name or leak term (`tests/test_memos_notes.py`).

## Blind-memo preparation (for Stage 5)

- **Removed from blind copies:** decision; the whole "Why we invested/passed" section; founder and company names; founding years, cities, incubator; one hindsight phrase (memo 7, "later expanding into gold and lab-grown diamonds…"); one verdict sentence (memo 6, "That answer decided it: …"); verdict wording in memo 5 ("is what we backed") with the evidence kept.
- **Stage and source were also removed** because in this pack **stage perfectly predicts the decision** (all 6 invested memos say "Early round", all 6 passed say "Pre-seed"), and memo numbers alternate invested/passed. Blind IDs are shuffled (`MEMO-A`…`MEMO-L`).
- **Residual leak I cannot remove:** the 6 invested companies are real and well known (eVTOL from a university lab, retail bonds platform, silver jewellery D2C, small-town grocery rebranding, rural agri credit, warehouse sorting robots). A model may recognise them. The backtest report will state this.
- **Also leaking outcomes:** the partner notes and section 8 of `AIC_Rubric_v1.md`. The blind scorer will be given only `data/memos/blind/` and the criteria from config (rule added to CLAUDE.md).
- Redaction and deciding-criteria files are in `seed/curation/` (gitignored, they contain names and quotes). The "deciding criteria" mapping was written by me from each memo's own "Why we…" text; it is the comparison key, not a score.

## Assumed

1. **Claim extraction is model work, verified by code for existence, not for completeness.** Recall was checked for 40 key figures only. Lesser figures may be missing or mis-tagged; `other` holds 108 claims that fit no metric.
2. **Ranges keep only one end:** "3 to 4% a month" parses as 4%, "3 to 5 hours" as 3, "INR 9,000+" as 9,000. The words are kept in `as_written`; Stage 2 will not use these for checks.
3. **Some tags are the extractor's reading,** e.g. RentRoute deck "INR 11 L revenue" tagged gross (the form says it is gross); Settlr "1,150 SMEs" tagged `customers_live` (the documents don't say paying or active).
4. **Notes types are marker-based only** (e.g. "Decision:"). Rules such as "a missing number should drag the score" are recorded as notes, not interpreted.

## Extractor notes I checked and found wrong

Two agent comments were arithmetic slips: Pumpwise 140 sensors ÷ 6 customers = 23.3, which matches "average 23"; and RentRoute's chart 0.4 + 1.0 + 1.9 + 2.8 = 6.1 Cr, which matches the headline. Both reconcile. Stage 2 recomputes everything in code, so agent commentary is not used as evidence.

## Discrepancies already visible (to be confirmed in Stage 2, not scored here)

CAPilot 31 vs 24 paying; EarnWise team 12 vs 5, clients 3 vs 1, credentials (Goldman/Google/IIM-A vs internship/vendor contract/tier-2 MBA); StockSathi 38 vs 42 retailers, credit funded by own capital vs NBFC partner with first-loss, CAC 2,860 vs "under 2,000"; Talkbook MRR 2.1 L vs 1.9 L vs 340 × 500 = 1.7 L; Yatrika "thousands" vs ~1,300 travellers, no raise amount in deck; RentRoute deck shows gross revenue only.

## Open questions for you

1. **Settlr's TAM/SAM/SOM are payment volume, not revenue** (the deck says so). Should M1 compare volume-based markets on the same footing as revenue-based ones, or should I flag them as "volume TAM" separately? This affects Stage 2 labelling only, not the arithmetic.
2. **CareCorner's INR 40 L bank loan** is listed under existing investors in the form. I treat it as debt, not equity. Confirm.
