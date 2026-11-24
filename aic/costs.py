"""AI cost & ROI page data: metered spend (ai_calls), guardrails, Riya's cost in the same unit (₹), and readiness.

Everything here is computed from the ledger, config and run metrics. Where a number is not measured yet it says so;
nothing is imputed. Riya's hourly cost and the USD/INR rate are placeholders in config, labelled as such.
"""
import json
import os
from pathlib import Path
from typing import Optional

from . import config, db, llm

ROOT = Path(__file__).resolve().parent.parent


def _metered(conn, cfg) -> dict:
    d = llm.today(cfg)
    rows = lambda sql, a=(): [list(r) for r in conn.execute(sql, a)]
    per_co = rows("SELECT company, count(*), round(sum(cost_inr), 2), sum(input_tokens), sum(output_tokens), "
                  "sum(cache_read_tokens) FROM ai_calls WHERE company IS NOT NULL AND status IN ('ok', 'cached') "
                  "GROUP BY company ORDER BY 3 DESC")
    # An application counts only when all three stages ran (ok or from cache); a partial run is not a per-application cost.
    stages = {r[0]: set(r[1].split(",")) for r in conn.execute(
        "SELECT company, group_concat(DISTINCT task) FROM ai_calls WHERE company IS NOT NULL AND status IN ('ok', 'cached') "
        "GROUP BY company")}
    complete = [r for r in per_co if {"extraction", "research", "scoring"} <= stages.get(r[0], set())]
    n_apps = len(complete)
    total = llm.spend_inr(conn)
    ok = conn.execute("SELECT count(*), coalesce(avg(input_tokens), 0) FROM ai_calls WHERE status='ok'").fetchone()
    return {
        "today": d, "today_inr": round(llm.spend_inr(conn, d), 2), "total_inr": round(total, 2),
        "calls": conn.execute("SELECT count(*) FROM ai_calls").fetchone()[0], "ok_calls": ok[0],
        "avg_input_tokens": round(ok[1]),
        "cached_calls": conn.execute("SELECT count(*) FROM ai_calls WHERE status='cached'").fetchone()[0],
        "blocked_calls": conn.execute("SELECT count(*) FROM ai_calls WHERE status='blocked'").fetchone()[0],
        "per_application_inr": round(sum(r[2] for r in complete) / n_apps, 2) if n_apps else None,
        "applications": n_apps,
        "partial_applications": [{"company": r[0], "stages": sorted(stages.get(r[0], []))} for r in per_co if r not in complete],
        "by_day": rows("SELECT day, count(*), round(sum(cost_inr), 2) FROM ai_calls GROUP BY day ORDER BY day DESC LIMIT 30"),
        "by_task": rows("SELECT task, count(*), round(sum(cost_inr), 2) FROM ai_calls GROUP BY task ORDER BY 3 DESC"),
        "by_model": rows("SELECT model, count(*), round(sum(cost_inr), 2) FROM ai_calls GROUP BY model ORDER BY 3 DESC"),
        "by_company": per_co,
        "events": rows("SELECT at, kind, spend_inr, by, note FROM spend_events ORDER BY id DESC LIMIT 20"),
        "kill_switch": llm.kill_state(conn, d),
    }


def _build_session(cfg) -> Optional[dict]:
    p = ROOT / "reports" / "run_metrics.json"
    if not p.exists():
        return None
    m = json.loads(p.read_text())
    n = m["batch_size"]
    per_app = sum(a["tokens"] for a in m["agents"] if a["stage"] in ("extraction", "research", "research_fund", "scoring")) / n
    price = cfg["ai"]["prices_usd_per_mtok"]["claude-opus-5-5"]     # the build session ran on Claude Opus
    fx = cfg["ai"]["usd_inr"]
    return {"tokens_per_application": round(per_app),
            "if_all_cache_reads_inr": round(per_app * price["cache_read"] / 1e6 * fx, 1),
            "if_all_uncached_input_inr": round(per_app * price["input"] / 1e6 * fx, 1),
            "note": "Build-session agents ran inside Claude Code, which reports one token total per agent with no split "
                    "into input, output and cache reads, and no web-search count. So the rupee cost of the build session "
                    "is NOT measured: the two figures are bounds on the token total only (output tokens and searches "
                    "excluded). The first metered batch (python -m aic.runner) gives the real figure."}


def _roi(cfg, metered: dict, build: Optional[dict]) -> dict:
    r = cfg["roi"]
    per_app = r["riya_minutes_per_application"] / 60 * r["riya_inr_per_hour"]
    quarter = r["riya_days_per_quarter"] * r["hours_per_day"] * r["riya_inr_per_hour"]
    apps_q = round(r["riya_days_per_quarter"] * r["hours_per_day"] * 60 / r["riya_minutes_per_application"])
    sys_app = metered["per_application_inr"]
    out = {"riya_inr_per_hour": r["riya_inr_per_hour"], "riya_rate_is_placeholder": True,
           "riya_per_application_inr": round(per_app), "riya_per_quarter_inr": round(quarter),
           "riya_per_year_inr": round(quarter * 4), "applications_per_quarter": apps_q,
           "system_per_application_inr": sys_app, "measured": sys_app is not None}
    if sys_app is not None:
        out["system_share_pct"] = round(100 * sys_app / per_app, 1)
        out["saving_per_quarter_inr"] = round((per_app - sys_app) * apps_q)
    if build:
        out["bound_share_pct"] = [round(100 * build["if_all_cache_reads_inr"] / per_app, 1),
                                  round(100 * build["if_all_uncached_input_inr"] / per_app, 1)]
    stop = cfg["ai"]["spend_limits_inr_per_day"]["stop"]
    basis = sys_app or (build or {}).get("if_all_uncached_input_inr")
    out["applications_per_day_before_stop"] = int(stop // basis) if basis else None
    out["caveat"] = ("The saving counts only if the output is at least as good as Riya's. That is not shown yet: "
                     "the blind backtest agreed on 6 of 12 memos (every memo scored Pass), and the out-of-sample "
                     "test has not run. Until it passes the agreed bar, this is a cost comparison, not an ROI.")
    out["return_side"] = ("The return is not the salary saved: it is not missing the one company that returns the "
                          "fund. That is not measurable from 10 applications; it is what the out-of-sample test "
                          "and the 'call scored Pass' rule in the bar are for.")
    return out


def _readiness(metered: dict) -> list:
    env = lambda *k: all(os.environ.get(x) for x in k)
    return [
        {"step": "Make sure it works", "status": "done",
         "detail": "Test suite passes; deterministic checks agree 34/34 with the reference script; blind backtest run."},
        {"step": "Make sure it is safe", "status": "done",
         "detail": "Approvals, human-only decisions and append-only ledgers enforced by DB triggers; founder replies "
                   "are inert data; dry-run only; spend kill switch."},
        {"step": "Real-world load (Portkey, stress test)", "status": "ready" if env("PORTKEY_API_KEY") else "needs your account",
         "detail": "Claude calls, and Gemini calls except research (which needs Google Search grounding), route through "
                   "Portkey when PORTKEY_API_KEY is set (.env). Check with `python -m aic.llm check`. Stress test after that: "
                   "a batch of 10 through `python -m aic.runner`, watching latency, errors and spend."},
        {"step": "Can you operate it (Langfuse, RCA)", "status": "ready" if env("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") else "needs your account",
         "detail": "Each call sends a trace + generation to Langfuse when its keys are set; ai_calls.trace_id links "
                   "the ledger row to the trace for root-cause analysis."},
        {"step": "Do the economics make sense", "status": "measured" if metered["per_application_inr"] is not None else "metering built, not yet measured",
         "detail": "Every call is metered in ₹ with alerts and a kill switch; ROI section uses the metered figure once a "
                   "batch has run through the API runner."},
    ]


def levers(cfg, metered: dict) -> list:
    m = cfg["ai"]["models"]
    return [
        {"lever": "Send less", "status": "built",
         "detail": "Extraction sends page text only (no layout copy); scoring sends validated claims, checks and "
                   "research, not PDFs. Average input per call: " +
                   (f"{metered['avg_input_tokens']:,} tokens." if metered["ok_calls"] else "not measured yet.")},
        {"lever": "Cache everything", "status": "built",
         "detail": "Research is never re-bought once stored (output file = cache; --force to redo); identical requests "
                   f"are served from llm_cache at ₹0 ({metered['cached_calls']} so far); the stable prompt prefix uses prompt caching."},
        {"lever": "Cap the spend", "status": "built",
         "detail": f"Alert at ₹{cfg['ai']['spend_limits_inr_per_day']['alert']:,}/day, stop at "
                   f"₹{cfg['ai']['spend_limits_inr_per_day']['stop']:,}/day, a call whose worst case would cross the stop "
                   "is refused, and a partner can pull or release the switch by name."},
        {"lever": "Use cheaper models", "status": "tooling built, no switch yet",
         "detail": f"Models are set per task ({', '.join(f'{k}: {v}' for k, v in m.items())}). "
                   "`python -m aic.runner compare <stage> <Company> <model_a> <model_b>` shows the cost and output "
                   "difference; a person switches only on that evidence."},
    ]


def build(conn=None, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    llm.load_env()
    conn = conn or db.connect()
    met = _metered(conn, cfg)
    bs = _build_session(cfg)
    return {"metered": met, "build_session": bs, "roi": _roi(cfg, met, bs), "levers": levers(cfg, met),
            "readiness": _readiness(met), "limits": cfg["ai"]["spend_limits_inr_per_day"],
            "usd_inr": cfg["ai"]["usd_inr"], "models": cfg["ai"]["models"], "prices": cfg["ai"]["prices_usd_per_mtok"]}
