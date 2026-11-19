"""Out-of-sample test: does the screener agree with partners on applications they judged without seeing its scores?

  python -m aic.oos freeze <batch> <your name> <Company> [<Company> ...]   seal scores before partners decide
  python -m aic.oos decide <Company> <call|pass|hold|review_more> "<one-line reason>" <partner name>
  python -m aic.oos status <batch>
  python -m aic.oos evaluate <batch>                                         only once every company is decided

Rules, enforced in code and the DB:
  * freeze needs a computed score card for each company, no prior human decision on it, and no other batch holding it.
    A snapshot of each score card (and its SHA-256) is stored in append-only tables; evaluation uses the snapshot,
    so later rescoring cannot change the test.
  * While a batch is frozen and not yet evaluated, its companies are left off the dashboard (blind).
  * evaluate refuses unless every company has a named human decision made after the freeze, and every score card
    still matches its frozen hash. It runs once; the result is stored and cannot change.
  * The bar is config `oos_test` (a proposal for Kushal). Nothing here changes weights or thresholds.
"""
import hashlib
import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from . import config, db

ROOT = Path(__file__).resolve().parent.parent
SCORES = ROOT / "data" / "scores"
REPORTS = ROOT / "reports"
IST = ZoneInfo("Asia/Kolkata")
DECISIONS = ("call", "pass", "hold", "review_more")


class OOSError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="microseconds")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _latest_decision(conn, company: str):
    return conn.execute("SELECT human_decision, decided_by, decided_at, reason FROM outcomes "
                        "WHERE company=? AND human_decision IS NOT NULL ORDER BY decided_at DESC, id DESC LIMIT 1",
                        (company,)).fetchone()


# ---- freeze ---------------------------------------------------------------------
def freeze(conn, batch: str, by: str, companies: List[str], scores_dir: Path = SCORES, cfg: Optional[dict] = None) -> dict:
    cfg = cfg or config.load()
    if not companies:
        raise OOSError("a batch needs at least one company")
    if len(set(companies)) != len(companies):
        raise OOSError("duplicate company in batch")
    rows = []
    for co in companies:
        p = scores_dir / f"{co}.json"
        if not p.exists():
            raise OOSError(f"{co}: no score card; score it before freezing")
        if _latest_decision(conn, co):
            raise OOSError(f"{co}: partners already decided; it cannot be a blind test case")
        if conn.execute("SELECT batch FROM oos_members WHERE company=?", (co,)).fetchone():
            raise OOSError(f"{co}: already in a frozen batch")
        raw = p.read_text()
        sc = json.loads(raw)
        rows.append((batch, co, sc["band"], sc["total"], raw, hashlib.sha256(raw.encode()).hexdigest()))
    at = _now()
    try:
        conn.execute("INSERT INTO oos_batches (batch, frozen_at, frozen_by, bar) VALUES (?, ?, ?, ?)",
                     (batch, at, by, json.dumps(cfg["oos_test"])))
        conn.executemany("INSERT INTO oos_members (batch, company, band, total, score_json, score_sha) VALUES (?, ?, ?, ?, ?, ?)", rows)
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise OOSError(f"freeze failed: {e}")
    conn.commit()
    return {"batch": batch, "frozen_at": at, "companies": companies}


def blinded_companies(conn) -> set:
    """Companies in a frozen batch that has not been evaluated yet."""
    return {r[0] for r in conn.execute(
        "SELECT m.company FROM oos_members m LEFT JOIN oos_results r ON r.batch = m.batch WHERE r.batch IS NULL")}


# ---- partner decisions ------------------------------------------------------------
def decide(conn, company: str, decision: str, reason: str, by: str, at: Optional[str] = None) -> int:
    """Record a partner decision (a named human; the DB rejects model/system names and empty reasons)."""
    if decision not in DECISIONS:
        raise OOSError(f"decision must be one of {DECISIONS}")
    if not reason.strip() or "\n" in reason:
        raise OOSError("reason must be one line")
    row = conn.execute("SELECT id FROM outcomes WHERE company=? AND human_decision IS NULL ORDER BY id DESC LIMIT 1",
                       (company,)).fetchone()
    if row is None:
        row = (conn.execute("INSERT INTO outcomes (company, model_band, model_recommendation) VALUES (?, 'unscored', 'none')",
                            (company,)).lastrowid,)
    conn.execute("UPDATE outcomes SET human_decision=?, decided_by=?, decided_at=?, reason=? WHERE id=?",
                 (decision, by, at or _now(), reason.strip(), row[0]))
    conn.commit()
    return row[0]


# ---- status / evaluate ---------------------------------------------------------------
def _members(conn, batch: str):
    b = conn.execute("SELECT frozen_at, frozen_by, bar FROM oos_batches WHERE batch=?", (batch,)).fetchone()
    if not b:
        raise OOSError(f"no frozen batch {batch!r}")
    ms = conn.execute("SELECT company, band, total, score_sha, score_json FROM oos_members WHERE batch=? ORDER BY company",
                      (batch,)).fetchall()
    return b, ms


def status(conn, batch: str) -> dict:
    (frozen_at, frozen_by, _), ms = _members(conn, batch)
    out = {"batch": batch, "frozen_at": frozen_at, "frozen_by": frozen_by, "decided": [], "pending": [], "invalid": []}
    for co, *_rest in ms:
        d = _latest_decision(conn, co)
        if not d:
            out["pending"].append(co)
        elif d[2] is None or d[2] <= frozen_at:
            out["invalid"].append(f"{co}: decision not timestamped after the freeze")
        else:
            out["decided"].append(co)
    out["evaluated"] = bool(conn.execute("SELECT 1 FROM oos_results WHERE batch=?", (batch,)).fetchone())
    return out


def evaluate(conn, batch: str, scores_dir: Path = SCORES, reports_dir: Optional[Path] = REPORTS) -> dict:
    if conn.execute("SELECT 1 FROM oos_results WHERE batch=?", (batch,)).fetchone():
        raise OOSError(f"batch {batch!r} was already evaluated")
    (frozen_at, frozen_by, bar_json), ms = _members(conn, batch)
    bar = json.loads(bar_json)
    st = status(conn, batch)
    if st["pending"] or st["invalid"]:
        raise OOSError(f"not ready: pending {st['pending']}, invalid {st['invalid']}")
    rows = []
    for co, band, total, sha, snap in ms:
        if hashlib.sha256(snap.encode()).hexdigest() != sha:
            raise OOSError(f"{co}: frozen snapshot does not match its hash; the test is void")
        dec, by, at, reason = _latest_decision(conn, co)
        if dec in bar["excluded_decisions"]:
            result = "excluded"
        elif band in bar["no_commitment"]:
            result = "no_commitment"
        elif band in bar["agreement"].get(dec, []):
            result = "agree"
        else:
            result = "disagree"
        sc = json.loads(snap)
        rows.append({"company": co, "model_band": band, "model_total": total, "partner_decision": dec,
                     "decided_by": by, "decided_at": at, "partner_reason": reason, "result": result,
                     "model_reasons": sc.get("band_reasons", []),
                     "swing": [s["criterion"] for s in sc.get("swing_criteria", [])],
                     "who_was_wrong": None})
    counted = [r for r in rows if r["result"] != "excluded"]
    agree = sum(r["result"] == "agree" for r in counted)
    needed = math.ceil(bar["min_agree"] / bar["of"] * len(counted)) if counted else 0
    call_scored_pass = [r["company"] for r in rows if r["partner_decision"] == "call" and r["model_band"] == "pass"]
    passed = bool(counted) and agree >= needed and len(call_scored_pass) <= bar["call_scored_pass_allowed"]
    res = {"batch": batch, "frozen_at": frozen_at, "frozen_by": frozen_by, "evaluated_at": _now(), "bar": bar,
           "counted": len(counted), "agree": agree, "needed": needed,
           "disagree": sum(r["result"] == "disagree" for r in counted),
           "no_commitment": sum(r["result"] == "no_commitment" for r in counted),
           "excluded": len(rows) - len(counted), "calls_scored_pass": call_scored_pass,
           "meets_bar": passed, "rows": rows}
    conn.execute("INSERT INTO oos_results (batch, evaluated_at, result_json) VALUES (?, ?, ?)",
                 (batch, res["evaluated_at"], json.dumps(res)))
    conn.commit()
    if reports_dir is not None:
        write_report(res, reports_dir)
    return res


def write_report(res: dict, reports_dir: Path = REPORTS) -> Path:
    L = [f"# Out-of-sample test: batch {res['batch']}", "",
         f"Frozen {res['frozen_at']} by {res['frozen_by']}; evaluated {res['evaluated_at']}. "
         "Partners decided without seeing the screener's scores (blinded on the dashboard).", "",
         f"**Result: {res['agree']} of {res['counted']} agree (bar: {res['needed']}); "
         f"{len(res['calls_scored_pass'])} partner calls scored Pass (allowed: {res['bar']['call_scored_pass_allowed']}). "
         f"{'Meets the bar.' if res['meets_bar'] else 'Does not meet the bar.'}**", "",
         f"Disagree: {res['disagree']} · no commitment (partner review): {res['no_commitment']} · excluded (review more): {res['excluded']}", "",
         "| Company | Screener band (total) | Partner decision | Result | Partner reason | Screener reasons |", "|---|---|---|---|---|---|"]
    for r in res["rows"]:
        L.append(f"| {r['company']} | {r['model_band']} ({r['model_total']:.0f}) | {r['partner_decision']} by {r['decided_by']} | "
                 f"{r['result']} | {r['partner_reason']} | {'; '.join(r['model_reasons'])} |")
    L += ["", "## For each disagreement: who was wrong?", "",
          "Left for the partners to fill in once the outcome is known (the screener, the partners, or too early to say). "
          "Record score changes as corrections (`python -m aic.feedback add ...`) so they count next time.", ""]
    for r in res["rows"]:
        if r["result"] == "disagree":
            L.append(f"- **{r['company']}**: screener {r['model_band']}, partners {r['partner_decision']}. "
                     f"Criteria most likely to move it: {', '.join(r['swing']) or 'n/a'}. Who was wrong: ____")
    p = reports_dir / f"oos_{res['batch']}.md"
    p.write_text("\n".join(L) + "\n")
    return p


if __name__ == "__main__":
    a = sys.argv[1:]
    conn = db.connect()
    try:
        if a[:1] == ["freeze"] and len(a) >= 4:
            print(json.dumps(freeze(conn, a[1], a[2], a[3:]), indent=1))
        elif a[:1] == ["decide"] and len(a) == 5:
            print("recorded outcome", decide(conn, a[1], a[2], a[3], a[4]))
        elif a[:1] == ["status"] and len(a) == 2:
            print(json.dumps(status(conn, a[1]), indent=1))
        elif a[:1] == ["evaluate"] and len(a) == 2:
            r = evaluate(conn, a[1])
            print(f"{r['agree']}/{r['counted']} agree (needed {r['needed']}); meets bar: {r['meets_bar']}; report reports/oos_{a[1]}.md")
        else:
            print(__doc__)
    except OOSError as e:
        print("refused:", e)
        sys.exit(1)
