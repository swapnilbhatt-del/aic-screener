"""Application queue and volume test (case Task 2: "Send 20 applications into your system at once. Every one must end
up scored, queued, or marked 'needs attention' with a reason. None may disappear.").

  * enqueue: every application gets a `jobs` row (never deleted, DB trigger) in status 'queued'.
  * workers: at most `queue.workers` run at once; the rest wait their turn in the queue (FIFO).
  * each job runs extraction -> research -> scoring through the metered client (aic/llm.py: redaction, Portkey,
    Langfuse, kill switch). Each application is one Langfuse trace with a span per step and the generations inside.
  * outcomes:
      scored            all stages ran and every output passed its validator
      needs_attention   with a reason: the model refused, hit max tokens, returned no JSON, failed validation, or kept
                        failing after `queue.max_attempts` (a person looks at it; nothing is auto-rejected)
      queued            the daily spend stop paused the system; the job waits (reason says so) and resumes later
  * a transient failure (busy / rate limit / timeout) is retried by putting the job back in the queue.
  * reconcile: enqueued == scored + queued + needs_attention, or the run fails loudly.

  python -m aic.queue volume-test [--n 20] [--workers 4]     simulated model (replays stored outputs, injects faults)
  python -m aic.queue status <batch>
"""
import json
import random
import shutil
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from . import config, db, llm, runner

ROOT = Path(__file__).resolve().parent.parent
VT_DIR = ROOT / "data" / "volume_test"
TRANSIENT = ("503", "429", "high demand", "timed out", "timeout", "temporarily", "busy")


def now() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="milliseconds")


def _event(conn, job_id: int, status: str, note: str = "") -> None:
    conn.execute("INSERT INTO job_events (job_id, at, status, note) VALUES (?, ?, ?, ?)", (job_id, now(), status, note))


def enqueue(conn, batch: str, items: List[Dict[str, str]]) -> List[int]:
    """items: [{"label": unique name in the batch, "company": the application's input folder}]."""
    ids = []
    for it in items:
        jid = conn.execute("INSERT INTO jobs (batch, label, company, queued_at) VALUES (?, ?, ?, ?)",
                           (batch, it["label"], it["company"], now())).lastrowid
        _event(conn, jid, "queued", "received")
        ids.append(jid)
    conn.commit()
    return ids


def _claim(conn, batch: str) -> Optional[dict]:
    """Take the oldest queued job atomically (several workers may ask at once)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        r = conn.execute("SELECT id, label, company, attempts, queued_at FROM jobs WHERE batch=? AND status='queued' "
                         "ORDER BY id LIMIT 1", (batch,)).fetchone()
        if not r:
            conn.execute("COMMIT")
            return None
        conn.execute("UPDATE jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=?", (now(), r[0]))
        _event(conn, r[0], "running", f"attempt {r[3] + 1}")
        conn.execute("COMMIT")
        return {"id": r[0], "label": r[1], "company": r[2], "attempt": r[3] + 1, "queued_at": r[4]}
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _finish(conn, job_id: int, status: str, reason: Optional[str], cost: float = 0.0, trace_id: Optional[str] = None):
    conn.execute("UPDATE jobs SET status=?, reason=?, cost_inr=cost_inr+?, trace_id=coalesce(?, trace_id), "
                 "finished_at=CASE WHEN ? IN ('scored', 'needs_attention') THEN ? ELSE finished_at END WHERE id=?",
                 (status, reason, cost, trace_id, status, now(), job_id))
    _event(conn, job_id, status, reason or "")
    conn.commit()


def run_job(conn, job: dict, *, stages=runner.STAGES, out_root: Path, client=None, max_attempts: int = 2,
            stop: threading.Event, tags: Optional[list] = None) -> str:
    trace_id = llm.new_trace_id()
    root = llm.new_span_id()
    t0 = time.time()
    try:
        qt = datetime.fromisoformat(job["queued_at"]).timestamp()
    except ValueError:
        qt = t0
    llm.trace_step(trace_id, "queue wait", qt, t0, parent_span_id=root, attrs={"attempt": job["attempt"]})
    cost, outcome, reason = 0.0, "scored", None
    for stage in stages:
        s0, sid = time.time(), llm.new_span_id()
        try:
            r = runner.run(conn, stage, job["company"], force=True, out_base=out_root / f"job{job['id']}",
                           client=client, trace={"trace_id": trace_id, "parent_span_id": sid, "tags": tags or []},
                           use_cache=False)
            cost += r["cost_inr"]
            err = "; ".join(r["validation_errors"][:2]) if r["validation_errors"] else None
            llm.trace_step(trace_id, stage, s0, time.time(), span_id=sid, parent_span_id=root,
                           attrs={"prompt_version": r["prompt_version"], "cost_inr": r["cost_inr"]},
                           error=f"validation: {err}" if err else None)
            if err:
                outcome, reason = "needs_attention", f"{stage} output failed validation: {err}"
                break
        except llm.SpendStopped as e:
            llm.trace_step(trace_id, stage, s0, time.time(), span_id=sid, parent_span_id=root, error=f"paused: {e}")
            stop.set()
            outcome, reason = "queued", f"paused before {stage}: {e}. Resumes when the limit resets or a named person releases it"
            break
        except Exception as e:                                 # anything else must still land somewhere, with a reason
            msg = f"{type(e).__name__}: {e}"[:300]
            llm.trace_step(trace_id, stage, s0, time.time(), span_id=sid, parent_span_id=root, error=msg)
            if any(t in msg.lower() for t in TRANSIENT) and job["attempt"] < max_attempts:
                outcome, reason = "queued", f"retry after transient error in {stage}: {msg}"
            else:
                outcome, reason = "needs_attention", f"{stage} failed" + (
                    f" after {job['attempt']} attempts" if job["attempt"] > 1 else "") + f": {msg}"
            break
    llm.trace_step(trace_id, f"application {job['label']}", t0, time.time(), span_id=root,
                   attrs={"company": job["company"], "outcome": outcome, "reason": reason or "", "cost_inr": round(cost, 4)},
                   error=reason if outcome == "needs_attention" else None,
                   trace_name=f"aic.application.{job['label']}", tags=["aic-screener", "application"] + (tags or []))
    _finish(conn, job["id"], outcome, reason, cost, trace_id)
    if outcome == "queued" and reason and reason.startswith("paused"):
        conn.execute("UPDATE jobs SET attempts=attempts-1 WHERE id=?", (job["id"],))   # a pause is not a failed attempt
        conn.commit()
    return outcome


def process(db_path: Path, batch: str, *, workers: int = 4, client_factory: Optional[Callable] = None,
            stages=runner.STAGES, out_root: Path, max_attempts: int = 2, tags: Optional[list] = None) -> dict:
    """Drain the queue with at most `workers` jobs in flight. Stops taking new jobs once the spend stop trips."""
    stop = threading.Event()
    live, peak, lock = [0], [0], threading.Lock()

    def worker(_):
        conn = db.connect(db_path)
        client = client_factory() if client_factory else None
        while not stop.is_set():
            job = _claim(conn, batch)
            if job is None:
                return
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            try:
                run_job(conn, job, stages=stages, out_root=out_root, client=client, max_attempts=max_attempts,
                        stop=stop, tags=tags)
            finally:
                with lock:
                    live[0] -= 1
        conn.close()

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(worker, range(workers)))
    return {"wall_seconds": round(time.time() - t0, 1), "peak_in_flight": peak[0], "workers": workers}


def summary(conn, batch: str) -> dict:
    rows = [dict(zip(("id", "label", "company", "status", "reason", "attempts", "cost_inr", "trace_id", "queued_at",
                      "started_at", "finished_at"), r)) for r in conn.execute(
        "SELECT id, label, company, status, reason, attempts, cost_inr, trace_id, queued_at, started_at, finished_at "
        "FROM jobs WHERE batch=? ORDER BY id", (batch,))]
    c = Counter(r["status"] for r in rows)
    enq = conn.execute("SELECT count(*) FROM job_events e JOIN jobs j ON j.id=e.job_id WHERE j.batch=? AND e.note='received'",
                       (batch,)).fetchone()[0]
    accounted = c["scored"] + c["queued"] + c["needs_attention"]
    return {"batch": batch, "enqueued": enq, "scored": c["scored"], "queued": c["queued"],
            "needs_attention": c["needs_attention"], "running": c["running"], "lost": enq - accounted - c["running"],
            "retries": sum(max(0, r["attempts"] - 1) for r in rows), "jobs": rows}


# ---- simulated model for the volume test --------------------------------------------------------------------
class ReplayGemini:
    """Stands in for the model: answers each stage with that application's stored output (so validators run on real
    data), with a short random delay, and injects the failures a real batch meets. No money is spent."""
    gateway_name = "simulated"
    STORED = {"extraction": "claims/{c}.raw.json", "research": "research/{c}.json", "scoring": "scores/raw/{c}.json"}

    def __init__(self, faults: Dict[str, str], usage=(2000, 400), delay=(0.05, 0.25), seed=7):
        self.faults, self.usage, self.delay, self.seen = faults, usage, delay, Counter()
        self.rng = random.Random(seed)

    @staticmethod
    def _stage(body: dict) -> str:
        if body.get("tools"):
            return "research"
        user = body["contents"][0]["parts"][0]["text"]
        return "extraction" if '"deck_pages"' in user else "scoring"

    def generate(self, model, body):
        time.sleep(self.rng.uniform(*self.delay))
        stage = self._stage(body)
        payload = json.loads(body["contents"][0]["parts"][0]["text"])
        label = payload.get("_job_label") or payload["company"]
        co = payload["company"]
        fault = self.faults.get(f"{label}:{stage}") or self.faults.get(label)
        self.seen[(label, stage)] += 1
        text, finish = (runner.DATA / self.STORED[stage].format(c=co)).read_text(), "STOP"
        if fault == "busy_once" and sum(v for (l, _), v in self.seen.items() if l == label) == 1:   # first call only
            raise llm.ModelError("Gemini HTTP 503: This model is currently experiencing high demand")
        if fault == "busy_always":
            raise llm.ModelError("Gemini HTTP 503: This model is currently experiencing high demand")
        if fault == "no_json":
            text = "I'm sorry, I can't produce that file."
        if fault == "invalid":
            text = json.dumps({"company": co})
        if fault == "max_tokens":
            finish = "MAX_TOKENS"
        if fault == "refusal":
            finish = "SAFETY"
        return {"responseId": f"sim-{label}-{stage}", "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
                "usageMetadata": {"promptTokenCount": self.usage[0], "candidatesTokenCount": self.usage[1]}}


DEFAULT_FAULTS = {  # what a real batch meets; each must end in the right place with a reason
    "CAPilot#2": "busy_once",            # transient 503 -> back in the queue -> scored on retry
    "EarnWise#2:research": "busy_always",  # keeps failing -> needs attention after max attempts
    "GrainKind#2:scoring": "no_json",     # model returns prose, not JSON -> needs attention
    "Pumpwise#2:research": "invalid",     # output fails the research validator -> needs attention
    "RentRoute#2:extraction": "max_tokens",  # cut off -> needs attention, nothing written
    "Settlr#2:scoring": "refusal",        # model refuses -> needs attention
}


def volume_test(n: int = 20, workers: int = 4, faults: Optional[Dict[str, str]] = None, pause_stop_inr: float = 12.0,
                out: Path = VT_DIR, send_traces: bool = True) -> dict:
    """20 applications at once against a fresh DB with a simulated model, in two phases:
    1. a low simulated daily stop, so the system pauses partway and the rest wait in the queue with a reason;
    2. the limit resets (standing in for the next day; the configured stop applies) and the same queue drains.
    Every application must end scored or needs_attention, and none may be lost."""
    import os
    cos = runner.companies()
    # interleave so injected faults are met early, as they would be in a real mixed batch
    order = [f"{c}#2" for c in cos] + [f"{c}#1" for c in cos]
    order = [x for pair in zip(order[:len(cos)], order[len(cos):]) for x in pair][:n]
    items = [{"label": lab, "company": lab.split("#")[0]} for lab in order]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    dbp = out / "volume.db"
    base = config.load()
    conn = db.connect(dbp)
    batch = f"volume-{datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d-%H%M%S')}"
    enqueue(conn, batch, items)
    faults = DEFAULT_FAULTS if faults is None else faults
    labels = threading.local()
    orig_load, orig_build, orig_run_job, orig_today = config.load, runner.build_request, run_job, llm.today

    def tagged_build(stage, company, conn=None):
        req = orig_build(stage, company, conn=conn)
        lab = getattr(labels, "label", None)
        if lab:
            p = json.loads(req["messages"][0]["content"])
            p["_job_label"] = lab
            req["messages"] = [{"role": "user", "content": json.dumps(p, ensure_ascii=False)}]
        return req

    def labelled_run_job(conn_, job, **kw):
        labels.label = job["label"]
        return orig_run_job(conn_, job, **kw)

    saved = {k: os.environ.pop(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if k in os.environ and not send_traces}
    model = ReplayGemini(faults)
    phases = []
    try:
        runner.build_request = tagged_build
        globals()["run_job"] = labelled_run_job
        for name, stop in (("1: low daily stop", pause_stop_inr), ("2: limit reset (next day)", base["ai"]["spend_limits_inr_per_day"]["stop"])):
            cfg = json.loads(json.dumps(base))
            cfg["ai"]["spend_limits_inr_per_day"] = {"alert": round(stop / 2, 2), "stop": stop}
            config.load = lambda *a, _c=cfg, **k: _c          # the simulated limit applies inside this test only
            perf = process(dbp, batch, workers=workers, client_factory=lambda: model, out_root=out / "outputs",
                           tags=["volume-test", "simulated"])
            snap = summary(conn, batch)
            phases.append({"phase": name, "stop_inr": stop, **perf,
                           **{k: snap[k] for k in ("scored", "queued", "needs_attention", "lost")},
                           "queued_reasons": sorted({j["reason"].split(":")[0] for j in snap["jobs"] if j["status"] == "queued" and j["reason"]})})
            if not snap["queued"]:
                break
            # Next day: an automatic stop applies only to its own day and the daily total starts again at zero, so
            # moving the simulated clock on is enough. Nobody "releases" anything (that needs a named person).
            llm.today = lambda c, n=None: "2099-01-01"
    finally:
        config.load, runner.build_request = orig_load, orig_build
        globals()["run_job"] = orig_run_job
        llm.today = orig_today
        os.environ.update(saved)
    s = summary(conn, batch)
    s.update({"phases": phases, "simulated": True, "faults_injected": faults, "workers": workers,
              "wall_seconds": round(sum(p["wall_seconds"] for p in phases), 1),
              "peak_in_flight": max(p["peak_in_flight"] for p in phases),
              "spend_inr": round(llm.spend_inr(conn), 4),
              "model_calls": conn.execute("SELECT count(*) FROM ai_calls WHERE status IN ('ok', 'error')").fetchone()[0],
              "blocked_calls": conn.execute("SELECT count(*) FROM ai_calls WHERE status='blocked'").fetchone()[0],
              "langfuse_traces": sum(1 for j in s["jobs"] if j["trace_id"]) if send_traces else 0,
              "note": ("Simulated model: each call replays the application's stored output (so the real validators run) "
                       "with injected faults. No model was paid. Phase 1 lowers the daily stop to show the pause; "
                       "phase 2 stands in for the next day.")})
    if s["lost"] != 0 or s["running"] != 0:
        raise RuntimeError(f"volume test lost {s['lost']} application(s)")
    (out / "result.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
    conn.close()
    return s


if __name__ == "__main__":
    llm.load_env()
    a = sys.argv[1:]
    if a[:1] == ["volume-test"]:
        n = int(a[a.index("--n") + 1]) if "--n" in a else 20
        w = int(a[a.index("--workers") + 1]) if "--workers" in a else 4
        r = volume_test(n, w)
        print(json.dumps({k: v for k, v in r.items() if k != "jobs"}, indent=1))
        for j in r["jobs"]:
            print(f"{j['label']:14} {j['status']:16} attempts={j['attempts']} {j['reason'] or ''}"[:200])
    elif a[:1] == ["status"] and len(a) == 2:
        print(json.dumps(summary(db.connect(), a[1]), indent=1))
    else:
        print(__doc__)
