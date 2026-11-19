# Out-of-sample test harness

The backtest in `stage5.md` is in-sample: the rubric was built from those memos. This harness tests the screener
on applications it has never seen, against partner decisions made without seeing its scores.

## How to run it on the next batch

1. **Ingest and score the new applications** as usual. Add the companies to `aic/ingest.py` `COMPANIES`, then run
   Stages 1–4. Do not open their score cards.
2. **Freeze before anyone decides:**
   `python -m aic.oos freeze next10 <your name> <Company> <Company> ...`
   Each company's score card is snapshotted, hashed and stored in append-only tables, and the company disappears from
   the dashboard (a notice lists the blinded names). Freezing is refused for a company that has no score card,
   already has a partner decision, or is already in another batch.
3. **Partners read the applications and decide, without the screener:**
   `python -m aic.oos decide <Company> <call|pass|hold|review_more> "<one-line reason>" <partner name>`
   A model, system or blank name is rejected by the database.
4. **Check progress:** `python -m aic.oos status next10`. This shows decided, pending, and invalid (decided before the freeze).
5. **Evaluate once every company is decided:** `python -m aic.oos evaluate next10`.
   - Refused while anything is pending or invalid.
   - Runs once; the result is stored and cannot change.
   - Uses the frozen snapshots, so rescoring afterwards cannot alter the test.
   - Writes `reports/oos_next10.md`.

## The bar (proposal in `config/rubric.yaml` → `oos_test`; Kushal to agree or change)

- **Agreement:** at least **8 of 10** must agree, scaled to the number counted.
- **Calls:** **no** company the partners call may be scored Pass.
- **What counts as agreeing:** a partner call matches a Call band; a partner pass matches a Pass or Hold band; a partner hold matches a Hold band.
- **Neither:** a Partner review band is "no commitment" and doesn't count as agreeing. A "review more" decision is excluded.

The report leaves "who was wrong" blank for each disagreement, for the partners to fill in when the outcome is
known. Score changes go into the corrections log so they count next time.

## Why the current 10 cannot be the test

Their scores and bands are already published (dashboard, Vercel site), so a partner deciding now may have seen
them. The harness only accepts companies with no prior decision, but it cannot know who has looked at a public page.
Use genuinely new applications.
