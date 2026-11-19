# Stage 4 run report: scoring

Date: 2026-11-19. Command: `python -m aic.scoring`, then `python -m aic.compare_prior`. Tests: 274 passed.
Per-company score cards with every evidence item, citation, URL and access date: `data/scores/<Company>.json` (gitignored). The outcomes table holds one **undecided** row per company. A named human decides; the DB rejects anything else.

## How a score is made

1. **Five scoring agents** (two companies each) proposed 0–5 scores per criterion, following `prompts/score.md`, from the Stage 1–3 outputs only. They did not see your prior scores, the memos or the notes.
2. **Code validates each proposal:**
   - every evidence reference must resolve to a claim, check, research finding or form field;
   - quotes must appear in the cited source;
   - a "missing" criterion must score 0 and be marked unknown;
   - T2 must equal its number of disclosed sub-parts;
   - rubric anchors are enforced: S2 ≤ 1 with a material contradiction, and M1 ≤ 1 when a market or assumption check fails. A file that breaks a rule is rejected, not silently changed.
3. **Code applies these rules and logs each change:**
   - T2 sub-part rule (provisional, see Q1);
   - founder evidence cap: F ≤ 4 with no outside confirmation;
   - pedigree cap: F1 ≤ 2 unless F2 or F3 ≥ 3.
4. **Code computes gates:**
   - G1 (Hold only for direct portfolio overlaps), G2c (sector vs public line) and G3 (stage) are computed;
   - G2a (regulator dependence), G2b (capital need), G4 (commitment) and G5 (lending without a credit owner) come from the agents with evidence.
5. **Code computes points, subtotals, total, band, integrity cap, close call** (±5, inclusive), the two criteria most likely to move the band, and routing.

## Results

| Company | Total | Founder / 35 | Path / 35 | Band | Gates not clear | Integrity cap | Close call | Prior (v1) |
|---|---|---|---|---|---|---|---|---|
| GrainKind | 67 | 25 | 27 | **Hold** | G1 Hold (Taakat) | no | yes (70) | 70 Call |
| Pumpwise | 62 | 27 | 20 | **Partner review** | none | no | no | 75 Call |
| Talkbook | 51 | 21 | 17 | **Hold** | G1 Hold (MeetRecord) | yes (MRR) | yes (55) | 62 Hold |
| CareCorner | 50 | 24 | 15 | **Partner review** | G2c sector, G2b capex | no | yes (55) | 64 Partner review |
| RentRoute | 48 | 18 | 17 | **Partner review** | G2a regulatory dependence | no | no | 49 Pass |
| StockSathi | 48 | 21 | 14 | **Hold** | G1 Hold (SuperK), G5 lending | yes (count, credit) | no | 52 Pass |
| Settlr | 47 | 15 | 23 | **Hold** | G1 Hold (Mannjal), G3 Series A, G2b, G5 | no | no | 72 Call |
| CAPilot | 38 | 15 | 11 | **Pass recommendation** | none | yes (paying firms) | no | 53 Pass |
| Yatrika | 36 | 15 | 10 | **Pass recommendation** | none | yes (travellers) | no | 58 Partner review |
| EarnWise | 22 | 7 | 8 | **Partner review** | G2b advances book, G5 lending | yes (clients, team, credentials) | no | 24 Pass |

**No company reaches Call.** The highest unheld score is Pumpwise at 62. Unknown (missing data, scored 0): T2 for EarnWise and CareCorner.

### Adjustments code made (logged on each card)

- **Pedigree cap:** CAPilot F1 4→2, Settlr F1 3→2, Yatrika F1 3→2.
- **T2 "CAC by channel" rule (provisional):** CareCorner 1→0, RentRoute 2→1, Talkbook 3→2, Yatrika 2→1. Each had a blended CAC (plus a channel mix, or one paid channel) rather than costs per channel. Only GrainKind discloses CAC for several channels.
- **Founder evidence cap:** never fired, because no agent proposed a founder score above 4. The prompt mentioned the cap, so the agents may have anchored on it. Either way, no founder is confirmed by an outside source.

## Comparison with your prior scores (`reference/AIC_scores_v1.csv`)

Bands agree for 3 of 10 (Talkbook, CareCorner, CAPilot). Totals are lower for 9 of 10, by 1 to 25 points. Main reasons:

| Reason | Effect |
|---|---|
| Founder scores of 5 given without outside evidence (Pumpwise, Settlr, Talkbook, StockSathi, Yatrika) | now ≤ 4 per your decision; pedigree cap now applied (RentRoute's prior F1 4 already broke it) |
| M2 scored 1 where research found funded competitors the application omits | every company now scores M2 = 1 |
| M1 ≤ 1 enforced where a market formula or assumption check failed | GrainKind, Pumpwise, CareCorner, EarnWise, Settlr, Yatrika |
| T2 counted strictly by disclosed sub-parts | e.g. CareCorner 3→0, Pumpwise 4→2 |
| G1 Hold from the portfolio research | GrainKind, StockSathi, Settlr now on Hold (prior had only Talkbook) |
| Flag rule (s5) | RentRoute, EarnWise, CareCorner go to Partner review despite totals below 55 |

Pumpwise (75 → 62) loses most on T2 (no repeat data, blended CAC only, no LTV/CAC), T3 (no dated sequence) and M1 (the 60-sensor assumption vs 23 observed). Settlr (72 → 47) loses on founder scores, S1 (a Series A financing book) and the Hold.

## Verified

- **Totals and bands:** every total, subtotal and band is computed in code. A test recomputes them from the score cards.
- **Evidence:** every criterion scored above 0 cites evidence. Document evidence has a page cite; external evidence has a URL and access date (tested).
- **Engine tests:** 23 tests cover totals, both caps, T2 normalisation, anchors, gates, bands, close-call boundaries and rejection of unresolvable evidence. Mutating the flag rule, the integrity cap or the close-call margin each breaks at least one test.
- **Outcomes:** all are undecided in the DB, and the DB trigger blocks a non-human decision.

## Assumed / limitations

1. **F3 (candour)** is read from written text only, since there are no call notes. Confidence is low or medium everywhere.
2. **Scorer calibration:** five agents scored two companies each. They used the same prompt, but calibration across agents is not tested; the T2 inconsistency was one symptom, now normalised. A second independent scoring pass would measure agreement.
3. **Swing criteria:** "most likely to change" is a rule I chose: the lowest-confidence, highest-weight criteria with room to move toward the nearest threshold. It is shown, not used in any decision.
4. **G1 relies on the public portfolio list.** The fund's own list may add or remove holds.

## Open questions for you (each changes scores or bands)

1. **T2 "CAC by channel":** keep the literal rule (costs for 2 or more channels), or count a blended CAC plus a channel mix? The lenient reading adds 3 points each to CareCorner, RentRoute, Talkbook and Yatrika. No band changes either way.
2. **T2 other sub-parts, as the agents read them:**
   - CAPilot's churn count (2 firms) was counted as "repeat or cohort" data;
   - RentRoute's gross margin was derived from fee minus partner cost;
   - StockSathi's 4% trade margin was not counted as gross margin.
   Keep, or set a rule?
3. **Flags below 55.** Rubric s5 says Partner review applies to "any score where a Flag is open". G2 says (a) or (b) means "Flag for pass recommendation". I followed s5 literally, so RentRoute (48), CareCorner (50) and EarnWise (22) show **Partner review**, with "score band: pass" in the reasons. Should a flagged company below 55 show Pass recommendation with the flag attached instead?
4. **Settlr's Hold on Mannjal** rests on conflicting descriptions of Mannjal. Settlr is also a Series A outside stage (G3), so it would reach Partner review anyway. Keep the Hold?
