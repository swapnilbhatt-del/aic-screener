# AIC Screener

Pre-seed screening for All In Capital: scores each application against the rubric with cited evidence and
recommends. **Partners decide; the system never decides.** Constraints and enforcement: see `CLAUDE.md`.

## Run order

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m aic.ingest            # Stage 1: text, forms, claims (needs data/claims/*.raw.json), memos, notes
.venv/bin/python -m aic.checks            # Stage 2: deterministic checks
.venv/bin/python -m aic.research briefs   # Stage 3: briefs for research agents (cache in data/research/)
.venv/bin/python -m aic.scoring           # Stage 4: scores from data/scores/raw/*.json; undecided outcomes in DB
.venv/bin/python -m aic.backtest unseal   # Stage 5: only after 'score' wrote the manifest
.venv/bin/python -m aic.feedback list     # Stage 6: corrections (add / surface / propose)
.venv/bin/python -m aic.outreach status   # Stage 7: dry-run outreach (approve-email / approve-hold / allow)
.venv/bin/python -m aic.assurance         # trust & limits, what's missing, time & cost
.venv/bin/python -m aic.oos status <batch> # out-of-sample test: freeze / decide / status / evaluate (reports/oos_harness.md)
.venv/bin/python -m aic.runner scoring <Co> # model stages as metered API calls (extraction / research / scoring / compare)
.venv/bin/python -m aic.llm spend         # AI spend today and to date; stop / release the kill switch
.venv/bin/python -m aic.dashboard         # dashboard/index.html (local); --site for site/, --artifact for the Claude page
.venv/bin/python -m pytest -q
```

Serve the dashboard locally so source-PDF links resolve:
`.venv/bin/python -m http.server 8790 --bind 127.0.0.1` then open `http://127.0.0.1:8790/dashboard/index.html`.

Model work (claim extraction, research, scoring proposals) is done by agents following `prompts/`; every number,
total, cap, band and gate is computed and validated in code. `seed/`, `data/`, `outbox/` and `dashboard/*.html`
contain founder data and are gitignored. Run reports: `reports/stage0.md` to `reports/stage7.md`.

API keys: copy `.env.example` to `.env` (gitignored). Cost, ROI and Portkey/Langfuse setup: `reports/production_readiness.md`.

Feedback loop and fine-tuning readiness: `python -m aic.learning disagreement|readiness|export [--per-criterion]`; record an email edit with `python -m aic.outreach edit`, flag bad-day feedback with `python -m aic.feedback flag`; train with `notebooks/unsloth_finetune.ipynb` in Colab (see `reports/feedback_and_finetuning.md`).

Hand-over checks (Case 04): `python -m aic.audit` (what each model call sends), `python -m aic.queue volume-test` (20 applications at once, none lost); see `reports/handover_readiness.md`.

Public deployment: `python -m aic.dashboard --site`, copy `site/` to a folder named `aic-screener`, then `vercel deploy --prod --yes` there (live at https://aic-screener.vercel.app). Requirements audit: `reports/requirements_audit.md`.
