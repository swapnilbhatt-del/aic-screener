# Stage 2 run report: deterministic checks

Date: 2026-11-19. Commands: `python -m aic.checks`, `python -m aic.reference_reconcile`. Tests: 211 passed.
Full per-check detail with every input and citation: `data/checks/<Company>.json` (gitignored).

## Counts

143 checks: **115 PASS, 27 FAIL, 1 UNCHECKABLE.**

| Company | PASS | FAIL | Unchecked | Material cross-document contradictions |
|---|---|---|---|---|
| CAPilot | 8 | 1 | 0 | 1 |
| CareCorner | 11 | 1 | 0 | 0 |
| EarnWise | 4 | 5 | 0 | 3 |
| GrainKind | 14 | 3 | 1 | 0 |
| Pumpwise | 22 | 1 | 0 | 0 |
| RentRoute | 11 | 1 | 0 | 0 |
| Settlr | 13 | 5 | 0 | 0 |
| StockSathi | 13 | 3 | 0 | 1 (+1 open question) |
| Talkbook | 16 | 5 | 0 | 1 |
| Yatrika | 3 | 2 | 0 | 1 |

## How checks work

- **Four kinds**, reported separately (the reference script mixed them):
  - `formula`: the deck's own arithmetic, e.g. TAM = count × spend
  - `cross_document`: deck vs form
  - `assumption_vs_observed`: a market or plan assumption vs the company's own observed data
  - `internal`: other self-consistency, such as chart sums, MRR = seats × price, and payback
- **Every input is a claim from Stage 1** with its citation, or an explicit constant with its reason (e.g. "12 months").
- **Tolerance** is 5% from config, inclusive. Stated bounds are respected: "< 4 months", "under INR 2,000", "INR 40,000+".
- **Cross-document comparisons** use the headline (largest) figure each document gives for the metric.
- **Credentials** are compared per founder. Named institutions and employers (capitalised names, acronyms) and stated durations must appear in both documents. "CA" and "Chartered Accountant" are treated as the same.
- **Missing inputs give UNCHECKABLE** with the reason. Nothing is imputed.
- **Curated checks:** 3 are text contradictions or omissions I selected by reading; they are marked `curated` and need a human to confirm. All other verdicts are computed.
- **Material** follows your default: only contradictions between sources on traction, revenue, team, credentials or raise. Omissions are FAIL but not material.

## Reconciliation with `reference/aic_arithmetic_checks.py`

Your script runs unchanged and each of its 34 rows maps to a Stage 2 check. **34 of 34 agree on PASS/FAIL.** Its arithmetic is correct. The differences are in labelling and coverage:

- 9 of its rows are not formula errors. They are cross-document checks (CAPilot paying firms, StockSathi CAC), assumption-vs-observed checks (EarnWise per-worker advance, Pumpwise sensors, Settlr volume per SME), or internal checks. Stage 2 labels them by kind.
- Stage 2 adds 109 checks, 12 of which fail. Your script had none of these, including StockSathi 38 vs 42 retailers, StockSathi credit funding, EarnWise team, clients and credentials, the Talkbook deck vs form MRR, Yatrika travellers and raise, CareCorner clinic run-rate, and the GrainKind SOM spend.

## Findings (all FAIL and UNCHECKABLE)

Material contradictions (these feed the integrity cap in Stage 4):

| Company | Check | Deck | Form |
|---|---|---|---|
| CAPilot | paying customers | 31 paying firms (p4, slide 5) | 24 paying + 7 free trial (p1). Deck = paying + trial exactly. |
| EarnWise | live enterprise clients | 3 (p5) | 1 live, 2 in pilot (p1) |
| EarnWise | team size | 12 (p7) | 5, incl. 2 outsourced developers (p1) |
| EarnWise | founder credentials | named employers and school (p7) | none of those names appear; different roles and durations (p1) |
| StockSathi | retailers onboarded | 38 (p5) | 42 (p2) |
| Talkbook | MRR | INR 2.1 L (p5) | INR 1.9 L (p1); 340 seats × INR 500 = INR 1.7 L, matching neither |
| Yatrika | travellers | "thousands" (p3) | about 1,300 (p1) |

Arithmetic and assumption failures (not caps, but they feed M1 and T2):

| Company | Check | Stated | Recomputed | Note |
|---|---|---|---|---|
| GrainKind | TAM / SAM | INR 91,200 Cr / 14,400 Cr | INR 9,120 Cr / 1,440 Cr | 10× overstated |
| GrainKind | SOM spend vs TAM spend | INR 2,400 / household | SOM uses INR 3,200 | same households, different spend |
| EarnWise | TAM | INR 14,400 Cr | INR 1.44 lakh Cr | 10× understated |
| EarnWise | advance per worker vs TAM | INR 12,000 / month | INR 594 / month | 20× gap; uses all enabled workers |
| Settlr | TAM / SAM / SOM (volume basis) | 9.4 / 1.8 lakh Cr / 6,750 Cr | 94.5 / 18 lakh Cr / 67,500 Cr | all 10× understated |
| Settlr | volume per SME vs TAM | INR 4.5 Cr / yr | INR 0.90 Cr / yr | 5× gap |
| Settlr | payback | 7 months | 3.7 months | deck method not stated; recomputed is more favourable |
| Pumpwise | TAM at observed sensors | INR 16,200 Cr (60 / firm) | INR 6,210 Cr (23 / firm) | 2.6× |
| CareCorner | clinic revenue vs maturity | INR 1.4 Cr / clinic / yr | INR 39 L run-rate | 3.6×; labelled "at maturity" |
| Talkbook | MRR from seats (deck, form) | 2.1 L, 1.9 L | 1.7 L | both fail |
| Talkbook | ARPU from seats | INR 13,000 | INR 10,625 | ARPU matches deck MRR / 16 instead |
| Talkbook | payback | ~5 months | 5.27 | fails 5% by 0.5 pts; within the stated precision (rounds to 5) |
| StockSathi | CAC deck vs form | "under INR 2,000" (form) | INR 2,860 (deck, Oct) | not a material field |
| StockSathi | credit funding (curated) | own capital, NBFC "in discussion" (deck p8) | through NBFC partner, company takes first loss, not an NBFC (form p2) | open question 1 |
| RentRoute | revenue basis (curated, omission) | deck shows INR 11 L gross only | form: net INR 5.5 L | omission |
| Yatrika | raise (omission) | deck gives no amount | INR 1.2 Cr | omission |
| GrainKind | LTV/CAC 1.8x | — | UNCHECKABLE | 12-month orders and LTV method not disclosed |

Notable passes: Pumpwise reproduces on every internal figure (MRR, hardware revenue, CAC, pilot conversion, first-year gross profit, payback < 4 months). StockSathi's and CareCorner's market formulas reproduce. RentRoute's chart sums to INR 6.1 Cr and both fee figures reproduce.

## Verified

- 34/34 agreement with your reference script, tested.
- Each of 68 named company checks has a test asserting its expected status. Every non-UNCHECKABLE check has a citation on every input (tested).
- Mutation check: forcing the comparison to always PASS makes 28 tests fail.

## Assumed

1. Cross-document comparison uses the largest figure in each document. Right for counts and headline revenue; could mislead where a document gives several figures for different periods. None did in this pack.
2. EarnWise per-worker advance divides by all 1,600 enabled workers over 4 months. The number of actual borrowers is not disclosed.
3. CareCorner run-rate uses October revenue across 3 clinics, including the newer clinics still ramping.
4. Settlr's market sizes are labelled volume-basis (your default).

## Open questions for you

1. **Is StockSathi's credit-funding contradiction material?** Deck: funded from own capital. Form: funded through an NBFC partner, with StockSathi taking first loss while not being an NBFC. It is not in your material list (traction, revenue, team, credentials, raise), so it does **not** trigger the integrity cap now. It does feed gate G5 and S2.
2. **Talkbook payback** misses the 5% tolerance by 0.5 points but rounds to the stated "~5 months". It stays a FAIL under the agreed rule. Should approximate figures ("~", "about") be judged at their stated precision instead?
3. **Should StockSathi's CAC contradiction be material?** CAC is not on the list, but the form states as current fact what the deck gives as a 12-month target.
