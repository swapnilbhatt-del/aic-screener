# Stage 0 run report: repo scaffold

Date: 2026-11-19

## Counts

| Item | Count |
|---|---|
| Seed PDFs copied (gitignored) | 22 (10 decks, 10 forms, 1 memo pack, 1 notes pack), 127 pages; hashes in `stage0_seed_manifest.json` |
| Reference files copied | 3 (rubric, prior scores, arithmetic script), unchanged |
| Tests | 36 passed, 0 failed |
| Mutation check | Removing the `outbox_requires_approval` trigger makes 4 gate tests fail, so the tests depend on the trigger |

## What was built

- `config/rubric.yaml`: weights (sum 100: founder 35, path 35, thesis 20, structure 10), thresholds 70/55, close-call ±5 inclusive, pedigree cap, integrity cap, gates, bands, routing, outreach settings. `aic/config.py` loads and validates it and refuses to load if weights ≠ 100, thresholds are inverted, a criterion is ungrouped, or `dry_run` is false.
- `aic/db.py`: SQLite schema with trigger-enforced gates:
  - emails: inserted only as drafts; `approved` or `sent` needs an unrevoked `send_email` approval for that exact row; `sent` must follow `approved`; `sent` needs the recipient in `allowed_recipients` (empty by default); content is frozen once approved
  - calendar holds: same pattern with `create_calendar_hold` approvals; writing an `.ics` path counts as creating the hold
  - approvals: append-only, named human required (`model`, `system`, `auto`, `claude` and blank are rejected), can be revoked once
  - outcomes: created undecided; a decision needs a named human and a one-line reason
  - corrections table for Stage 6
- `CLAUDE.md`: the 7 constraints, how each is enforced, agreed defaults, working rules.

## Verified

- Weight totals and group subtotals match `AIC_Rubric_v1.md` section 3.
- Every gate rule above is covered by a test that tries to break it.
- Seed files match the zip contents one for one (22 of 22).

## Assumed (please confirm or correct)

1. **"Tuesday or Thursday afternoons" = 14:00 to 18:00 IST.** The notes don't give times.
2. **Gate G3 (stage) and the integrity cap's "material fields" list** come from your defaults; the exact field list is my wording.
3. **Approver names are free text.** Any non-blank name other than model/system/auto/claude is accepted. There is no login, so the DB cannot prove who typed the name.
4. **Git author** set repo-locally to your account email, since no global git identity exists.
5. **Seed renamed** to `applications/<Company>/{deck,form}.pdf`. StockSathi's form PDF was named "Form Response" and has a different header ("Inbound application 1 of 10", refers to a `.pptx` deck). The content is treated the same.

## Open questions / decisions for you

1. **Placeholder address:** `allowed_recipients` is empty, so every send fails. Add your test inbox when we reach Stage 7.
2. **Slide numbering:** deck PDFs print a slide number one higher than the PDF page (PDF page 2 shows "3"). For citations I plan to record both, as `p2 (slide 3)`. Tell me if you want only one.

## Not done in Stage 0

No parsing, scoring, research or outreach code yet. The DB file is created on first use under `data/` (gitignored).
