# All In Capital: Screening Rubric v1

**Status: DRAFT for agreement.** No score in this document should drive a real decision until Kushal has agreed the criteria, weights and thresholds. The brief asks for this to be "agreed in advance", so the thresholds below are proposals, not policy.

Origin tags used throughout: **[Memo n]** = past deal memo n, **[Notes mN]** = partner meeting notes, meeting N, **[Public]** = publicly available material (see Section 9), **[Own]** = my design choice, which the team should challenge.

---

## 1. What the rubric is built from

The fund does not publish a scoring rubric, so v1 is reconstructed from three kinds of evidence:

1. **The 12 deal memos** show what the fund actually rejected and backed, and why. Most criteria trace to a specific memo decision.
2. **The partner meeting notes** contain explicit rules that were stated in discussion, not written policy. Several are quoted or paraphrased below.
3. **Public material** (a 2023 Inc42 interview with Kushal, a third-party profile, press on Fund I and Fund II) gives the fund's stated framework. It is older and sometimes conflicts with the case text.

Where these sources disagree, the rubric shows the disagreement instead of picking a winner silently. Section 7 covers the one open question the notes leave unresolved.

---

## 2. Stage 0: Gates (flags, not scores)

Gates run before scoring. A gate never produces a score. It produces one of three states: **Clear**, **Flag** (a partner must decide), or **Hold** (no outreach until resolved).

| Gate | Test | Result | Origin |
|---|---|---|---|
| **G1 Conflict** | Does the company overlap a portfolio company? Check against the full list, not one remembered name. Default is no investing in competitors. | Overlap = **Hold** until the founder is told and the portfolio founder is spoken to. | [Notes m4], [Notes m4 rule] |
| **G2 Category or structure** | (a) Does the business only exist if a regulator changes its rules? (b) Does the model need far more capital than a pre-seed cheque can sustain? (c) Is it outside the fund's stated sectors? | (a) or (b) = **Flag** for pass recommendation. (c) = **Flag** for partner decision, since the public sector list is inconsistent (Section 9). | [Memo 4] HopBox, [Memo 10] Coinlane, [Public] |
| **G3 Stage** | Is the round pre-seed or early? | Later stage = **Flag**, not a rejection. | [Public], [Memo 1, 3, 5, 7, 9, 11] |
| **G4 Commitment** | Are both founders full-time and personally committed? | Not committed = **Flag**. | [Public] exclusion; founder commitment is a stated test |
| **G5 Regulated-lending exposure** | Does the company lend, or sit on a lending balance sheet? If so, does a founder own the credit risk? | No credit owner = **Flag** with the CampusCredit precedent. | [Memo 6] vs [Memo 11], [Notes m2] |

---

## 3. Stage 1: Scored criteria (100 points)

Each criterion is scored 0 to 5. Points = weight × score ÷ 5.

**Scoring anchors (apply to every criterion):**
- **5** = evidenced, specific, internally consistent, and checkable from an outside source
- **3** = specific and plausible, but unverified or partly consistent
- **1** = claimed without evidence, or contradicted by another part of the file
- **0** = missing. **A missing number scores 0, it is not skipped.** [Notes m1: "a missing number should drag the score, not be skipped"]

Each score must cite the evidence. A score with no citation is invalid.

### A. Founder: 35 points

| ID | Criterion | Weight | Scores 5 when | Scores 1 when | Origin |
|---|---|---|---|---|---|
| F1 | **Earned depth in this problem** | 10 | Years of direct, specific experience with this exact problem, with a visible "earned secret" (something they learned the hard way) | Credentials are general (school, brand names) and not tied to the problem | [Memo 1, 5, 9, 11], [Notes m3] "credentials are not a business. Score the evidence, not the pedigree." |
| F2 | **Owns the hardest risk** | 10 | The founder can explain and personally owns the function that decides survival (credit risk, unit economics, supply, regulation) | Dismisses it ("the NBFC handles that"), or no one on the team owns it | [Memo 2] no P&L, [Memo 6] "does not own risk", [Memo 8] "solved once the tech works", [Memo 11] |
| F3 | **Candour and specificity** | 10 | Names specific failures, specific customers, specific milestones; answers weak spots directly | Defensive on weak spots, vague milestones, or claims the market will sort itself out | [Memo 3] "described failures before we asked", [Memo 12] "defensive", [Notes m1] "a founder getting defensive … is information" |
| F4 | **Team completeness** | 5 | Every critical function has an owner (product, sales, ops, tech, and risk where relevant) | A critical function has no owner | [Memo 2] no ops co-founder, [Memo 8] weak commercial co-founder |

**Pedigree cap [Own, from Notes m3]:** F1 can score at most 2 unless F2 or F3 also scores 3 or more. Pedigree alone cannot carry the founder score.

### B. Path to market and evidence: 35 points

| ID | Criterion | Weight | Scores 5 when | Scores 1 when | Origin |
|---|---|---|---|---|---|
| T1 | **Traction quality** | 15 | Paid customers, live usage or volume, with pilots and paid users reported separately and counts that match across the deck and the form | Counts inflated (trials counted as paying), or only pilots and LOIs | [Memo 3] live sites, [Notes m3] paid vs pilot, [Own] count reconciliation |
| T2 | **Unit economics and retention disclosed** | 15 | Cohort or repeat data, CAC by channel, gross margin, payback, and LTV/CAC all present and consistent | Any of these missing scores 0 for the missing part | [Memo 2] repeat rate, [Memo 7] cohort repeat, [Notes m1] "no repeat data = drag the score" |
| T3 | **Path to revenue and milestones** | 5 | Dated milestone sequence, including regulatory or certification steps where relevant | "Solved once it works" | [Memo 1] milestone sequence vs [Memo 8] none, [Notes m3] |

### C. Thesis and market: 20 points

| ID | Criterion | Weight | Scores 5 when | Scores 1 when | Origin |
|---|---|---|---|---|---|
| M1 | **Market evidence reconciles** | 5 | Market formula reproduces the stated numbers, inputs are sourced, and the per-customer assumption matches observed usage | Formula does not reproduce the figure, or assumption contradicts observed data | [Memo 1] "we were not underwriting the market size" → low weight is deliberate; [Own] arithmetic check (see script) |
| M2 | **Defensibility and honest competition** | 10 | Real, named competitors (including funded ones) with a specific reason to win | "No direct competitors", or competitor set that omits funded incumbents | [Memo 2] crowded category, [Memo 12] defensibility, [Memo 6] |
| M3 | **Thesis fit and why now** | 5 | Fits the stated sector *and* the observed pattern of what the fund has backed; a clear "what changed" | Outside both | Public line vs observed pattern, see Section 7; [Public] "what has changed in the world" |

### D. Structure and integrity: 10 points

| ID | Criterion | Weight | Scores 5 when | Scores 1 when | Origin |
|---|---|---|---|---|---|
| S1 | **Capital structure fits the cheque** | 5 | Capital need is within a pre-seed cheque's ability to matter, with a sensible path | Needs density or balance-sheet capital the fund cannot provide | [Memo 4] HopBox, [Memo 1] sized the cheque to a slow path |
| S2 | **Evidence integrity** | 5 | Deck, form and public record agree on every material number | A material number is contradicted, or a claim is false | [Own] from brief ("every claim traceable"); see Section 5 cap |

**Total = 100.** A criterion with no evidence at all is scored 0 and marked **unknown** in the output, so that a score of 0 caused by missing data can be told apart from a score of 0 caused by a bad answer.

---

## 4. Scoring integrity rules

1. **Material contradiction cap [Own]:** if a material figure is contradicted between the deck, the form and the public record, the recommendation cannot be higher than "Partner review" until someone resolves it. The cap can only lower a band, never raise one.
2. **Close-call flag:** any score within 5 points of a threshold is marked "close call" and shown with the two criteria most likely to change it.
3. **Separate founder quality from path to market [Notes m3].** Founder criteria (F) and path criteria (T) are reported as separate subtotals. Riya had been mixing them. The output must show both.
4. **Show the work:** every criterion row carries its score, the evidence quote or figure with its location, and the source. Claims that came from outside the file carry their URL and access date.

---

## 5. Thresholds and recommendation states

These thresholds are **proposals to agree with Kushal**. The 70 threshold comes from the brief.

| Band | Score | What the system may recommend | What a human must do |
|---|---|---|---|
| **Call** | 70 or more, no gate Hold, no unresolved cap | "Move to call" | Kushal sees the outcome before any email (Notes m5). Riya reviews the draft. |
| **Partner review** | 55 to 69, or any score where a Flag is open | "Review" with the two or three specific gaps to resolve | Partner decides. No email by default. |
| **Pass recommendation** | Below 55 | "Pass" with a draft note for the partner | Partner decides. Nothing is auto-rejected (Notes m5). |
| **Hold** | Any Hold from a gate | "Hold" and the reason | Kushal resolves the conflict first. |

**Hard rules, from the notes:**
- **Nobody is auto-rejected or auto-advanced.** [Notes m5]
- **Deeptech second call is done by Aditya, not delegated.** [Notes m3]
- **Fintech and consumer first screens can run with Riya; Kushal gates the outcome.** [Notes m3]
- **Scheduled calls use Tuesday or Thursday afternoons, 30 minutes.** [Notes m5]

---

## 6. Recommendation states and what the output must contain

Every recommendation must state:
1. The band and total, with the founder and path subtotals shown separately.
2. Each gate result (Clear, Flag, Hold) and its reason.
3. Each criterion score with its evidence and citation.
4. What the file cannot tell us ("unknown" criteria).
5. The two criteria most likely to change the outcome.
6. Whether the close-call or contradiction cap applies.

---

## 7. The open question from Meeting 5: which thesis did I use?

The notes ask: "Riya asked if she should score against the written thesis or what we actually do. Kushal: 'tell me which one you used and why.'" The rubric answers it directly:

- **Gate G2 and the sector list use the public line** (fintech, deeptech, consumer tech, consumer brands), because it is what the fund says in public.
- **Criterion M3 uses the observed pattern** from the memos (founder-led, field-first, repeat-driven consumer, commerce infrastructure with real operators). Recent yeses such as SuperK and Wint would score low against the public wording but high against the observed pattern, which is exactly the drift Riya described.
- **Both are shown as separate fields.** If they disagree, the output says so. It does not pick one silently.

This is a choice I made, not a conclusion. Kushal and Aditya should decide whether M3 should stay as a combined field.

---

## 8. Backtest against the 12 memos

**Caveat, stated plainly:** this is a directional check made by reading each memo's reasoning. The memos contain no numeric scores, so I have **not** yet run the rubric blind against them. A real backtest needs each memo scored without its decision visible, then compared. That is the next step, and it is the only evidence that would justify trusting the rubric.

| Memo | Company | Decision | Criteria that decided it | Rubric direction | Consistent? |
|---|---|---|---|---|---|
| 1 | ePlane | Invested | F1, F3 high; T3 milestones; M1 low (market not underwritten) | Call | Yes |
| 2 | Petalry | Passed | T2 repeat missing (0); F2 no P&L owner | Pass | Yes |
| 3 | Unbox Robotics | Invested | F3 candour; T1 live sites | Call | Yes |
| 4 | HopBox | Passed | S1 capital structure; G2 | Flag, pass | Yes |
| 5 | Wint Wealth | Invested | F1 founder-market fit; M3 | Call | Yes |
| 6 | CampusCredit | Passed | F2 founder does not own risk | Pass | Yes |
| 7 | Giva | Invested | T2 cohort repeat and margin known | Call | Yes |
| 8 | AeroDrop | Passed | T1 no customer; T3 no regulatory path; F2 weak. Pedigree cap stops F1 carrying it. | Pass | Yes (Riya had scored 7.5) |
| 9 | SuperK | Invested | F1, F3, field evidence; T1 thin | Call, borderline | Close |
| 10 | Coinlane | Passed | G2 category | Gate, pass | Yes |
| 11 | Jai Kisan | Invested | F2 founders own risk, field-first | Call, with credit-hire condition | Yes |
| 12 | Prepnest | Passed | T2 retention missing (0); M2 weak defensibility; F3 defensive | Pass | Yes |

**Read this result carefully.** It suggests the rubric's *direction* matches the fund's past calls. It does not show the rubric's *numbers* are right, and it cannot show how often it would disagree with the partners on live deals. Kushal asked for exactly that measurement, so it must be run before any live use.

---

## 9. Public sources and where they conflict

| Source | Date | What it says | Conflict |
|---|---|---|---|
| Inc42 interview with Kushal Bhagia, "founder-market fit" | March 2023 | Only contra-bets, no safe bet at pre-seed. Founder-market fit = what founders know and can do, their key risk and their "earned secret". A "what has changed" test. Price and volume de-risk. Repeat founders are not automatically safer. | Dated (2023). Used as stated framework, not current policy. |
| F4 Fund profile | Undated | Sector-agnostic pre-seed/seed. Excludes founders unwilling to demonstrate full personal commitment. | Third-party summary. |
| Directory listings (privateequitylist, others) | Various | Fund II sectors include healthcare services, energy, agriculture, SaaS, e-commerce. | **Conflicts** with the case's public line (fintech, deeptech, consumer tech, consumer brands). |
| Press, 2022 to 2025 | Various | Fund I $10–11M and 51 startups. Fund II target ₹200 Cr, first close ₹85 Cr (March 2025). Average ticket about $150K. First cheques reported ₹2 to 5 Cr. Ran an AI-SaaS seed program. | Fund II is described as "currently raising" in the case. Press reports a first close in 2025. Not necessarily a conflict. |
| Portfolio (press and directories) | Various | Includes MeetRecord, Magma, Volt Money, SuprSend, CommandK, Produze, and others. | The pack's memos list six "invested" companies, which is not the full portfolio. **The full list is not in the seed data**, so G1 cannot be run completely. |

**What the sector conflict costs:** the rubric cannot tell whether a healthcare clinic is in or out of thesis. It can only flag the disagreement. That is why CareCorner gets a Flag, not a score-based decision.

---

## 10. Feedback loops this rubric depends on

**Correction log.** Every time Riya or Kushal changes a score or recommendation, record: company, criterion, model score, human score, one-line reason (Notes m5: "say why in a line so the correction can be reused"), and date.

**Reuse.** When a new company shares a sector and criterion with a past correction, show that correction on the card: "Last time on a similar company we moved F2 from 3 to 1 because the founder said default rates were the lender's problem."

**Governance.** Do not change weights or thresholds automatically. When the same kind of correction appears at least three times, propose a rubric change for partner approval. Weights only move when a person approves them.

**Outcome check.** Track passes and calls against what happened later (for example, Ledgerly and Prepnest, which the notes say may have been misses). That tells us whether the rubric is right, not just whether it is consistent.

---

## 11. Known gaps and what each one costs

| Gap | What it costs |
|---|---|
| **Full portfolio list not in the pack.** | G1 can only check the public names. The MeetRecord overlap was found only because the notes mention it. Any other overlap goes undetected. |
| **No call notes for the 10 new applicants.** | F3 (candour) is scored from written text only, which is less reliable than a live answer. Confidence on F3 is lower and must be shown as such. |
| **No cohort or bank data for most applicants.** | T2 scores 0 where the number is missing. That is the rule, but it means some good companies score low for lack of disclosure. |
| **No competitor list from the fund.** | M2 depends on my own research, which is partial and dated. Each competitor claim needs a source before it moves a score. |
| **Public thesis is partly outdated.** | The 2023 interview may not reflect the current fund. The partners need to confirm the thesis before the rubric is used. |
| **Ledgerly and the three uneasy passes are not in the pack.** | Those cases are the best test of the rubric and cannot be run yet. |
