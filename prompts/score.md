# Scoring instructions (Stage 4 applications; reused for Stage 5 blind memos)

You propose a 0–5 score for each rubric criterion, with evidence. **Code computes every total, band and cap.** You never add up points or recommend call/pass.

## Anchors (every criterion)

- **5** evidenced, specific, internally consistent, and checkable from an outside source
- **3** specific and plausible, but unverified or partly consistent
- **1** claimed without evidence, or contradicted by another part of the file
- **0** missing. A missing number scores 0 with `"unknown": true`. Never skip, never estimate.
- 2 and 4 sit between these. Score the evidence, not the pedigree.

## Criteria

| ID | Criterion | Scores 5 when | Scores 1 when |
|---|---|---|---|
| F1 | Earned depth in this problem | Years of direct, specific experience with this exact problem, with a visible "earned secret" | Credentials are general (school, brand names) and not tied to the problem |
| F2 | Owns the hardest risk | Founder can explain and personally owns the function that decides survival (credit risk, unit economics, supply, regulation) | Dismisses it ("the NBFC handles that"), or no one owns it |
| F3 | Candour and specificity | Names specific failures, customers, milestones; addresses weak spots directly | Defensive, vague milestones, or "the market will sort itself out" |
| F4 | Team completeness | Every critical function has an owner (product, sales, ops, tech, risk where relevant) | A critical function has no owner |
| T1 | Traction quality | Paid customers/live usage, pilots and paid reported separately, counts match across deck and form | Counts inflated (e.g. trials counted as paying), or only pilots/LOIs |
| T2 | Unit economics and retention disclosed | **Code-defined: 1 point per sub-part present:** `repeat_or_cohort`, `cac_by_channel`, `gross_margin`, `payback`, `ltv_cac`. A sub-part is present only if the figure is disclosed; an unmeasured one ("not measured yet") is absent. | — |
| T3 | Path to revenue and milestones | Dated milestone sequence, incl. regulatory/certification steps where relevant | "Solved once it works" |
| M1 | Market evidence reconciles | Formula reproduces, inputs sourced, per-customer assumption matches observed usage | Formula does not reproduce, or assumption contradicts observed data |
| M2 | Defensibility and honest competition | Real, named competitors incl. funded ones, with a specific reason to win | "No direct competitors", or a set that omits funded incumbents |
| M3 | Thesis fit and why now | Fits the stated sector **and** the observed pattern; clear "what changed" | Outside both |
| S1 | Capital structure fits the cheque | Capital need is within a pre-seed cheque's ability to matter | Needs density or balance-sheet capital the fund cannot provide |
| S2 | Evidence integrity | Deck, form and public record agree on every material number | A material number is contradicted, or a claim is false |

**M3:** report both `public_line_fit` (public sectors: fintech, deeptech, consumer tech, consumer brands) and `observed_pattern_fit` (what the fund has actually backed: founder-led, field-first, repeat-driven consumer, commerce infrastructure with real operators), each `fit`/`partial`/`outside`. Score M3 on both; say in the rationale if they disagree.

**Rules code will enforce** (your file is rejected if you break them): S2 ≤ 1 if any material cross-document check failed; M1 ≤ 1 if any market formula or assumption-vs-observed check failed; T2 = number of sub-parts present. Code will also cap founder criteria at 4 when no outside source confirms the founder, and apply the pedigree cap (F1 ≤ 2 unless F2 or F3 ≥ 3). Score what the evidence shows; do not pre-apply caps.

**F3 note:** there are no call notes for applicants; F3 is read from written text only. Set confidence to `medium` or `low` accordingly.

## Gates you assess (code assesses G1 portfolio, G2c sector, G3 stage)

- **G2a** the business exists only if a regulator changes (or keeps) a rule in its favour
- **G2b** the model needs far more capital than a pre-seed cheque can sustain (density, balance sheet, large capex)
- **G4** founders are not full-time or not personally committed
- **G5** the company lends, or carries credit risk on a lending book, and no founder clearly owns that credit risk

Each: `{"state": "clear"|"flag", "reason": "...", "evidence": [...]}`. Flag needs evidence.

## Evidence references

Every evidence item is `{"ref": "...", "point": "what it shows", "quote": "optional verbatim text from that source"}`. Allowed refs:

- `claim:<id>`: a Stage 1 claim in `data/claims/<Company>.json`
- `check:<id>`: a Stage 2 check in `data/checks/<Company>.json`
- `research:<id>`: a Stage 3 finding in `data/research/<Company>.json`; `research:_fund:<id>` for fund findings
- `form:<key>`: a parsed form field in `data/applications/<Company>.json` → `form_fields`
- `memo:<section>`: Stage 5 only (`what_it_does`, `founder_assessment`, `risks_and_open_questions`)

Code resolves each ref to its page, URL and access date. A ref that does not resolve, or a quote not found in it, rejects the file. Prefer 1–4 strong items per criterion. Low-confidence research findings are leads: do not let one alone move a score.

## Output: `data/scores/raw/<Company>.json`

```json
{
  "company": "<Company>", "scored_by": "subagent",
  "criteria": {
    "F1": {"score": 3, "unknown": false, "confidence": "medium", "rationale": "one line",
           "evidence": [{"ref": "claim:deck.team.x.exp", "point": "...", "quote": "..."}]},
    "T2": {"score": 2, "unknown": false, "confidence": "high", "rationale": "...", "evidence": [...],
           "subparts": {"repeat_or_cohort": {"present": true, "evidence": [...]},
                        "cac_by_channel": {"present": false, "evidence": []},
                        "gross_margin": {"present": true, "evidence": [...]},
                        "payback": {"present": false, "evidence": []},
                        "ltv_cac": {"present": false, "evidence": []}}},
    "M3": {"score": 4, "unknown": false, "confidence": "medium", "rationale": "...", "evidence": [...],
           "public_line_fit": "fit", "observed_pattern_fit": "partial"},
    "...": "all 12: F1 F2 F3 F4 T1 T2 T3 M1 M2 M3 S1 S2"
  },
  "gates": {"G2a": {...}, "G2b": {...}, "G4": {...}, "G5": {...}}
}
```

## Self-check (required)

`.venv/bin/python -m aic.scoring validate <Company>` until 0 errors. Report each criterion score with its one-line rationale, gate states, and anything you were unsure about.
