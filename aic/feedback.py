"""Stage 6: corrections log, reuse of past corrections, and weight-change proposals.

- A correction records: company, sector, criterion, model score (read from the score card), human score,
  one-line reason, who, when. The DB rejects non-human authors, unchanged scores, multi-line reasons,
  and any edit or deletion.
- surface(): past corrections from OTHER companies in the same sector on the same criterion, phrased for the card.
- propose(): when >= N corrections on one criterion move the same direction across distinct companies,
  write a candidate diff of config/rubric.yaml to the weight_proposals table. Nothing here writes the config.

  python -m aic.feedback add <Company> <Criterion> <human_score> "<reason>" <your name> [--this-case]
  python -m aic.feedback flag correction|email_edit <id> bad_day|retracted "<reason>" <your name>
  python -m aic.feedback lessons <Company>     what the scoring prompt would be given for this company
  python -m aic.feedback list
  python -m aic.feedback surface <Company>
  python -m aic.feedback propose
"""
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from . import config, db

ROOT = Path(__file__).resolve().parent.parent
SCORES = ROOT / "data" / "scores"
APPS = ROOT / "data" / "applications"
CONFIG_PATH = ROOT / "config" / "rubric.yaml"


class FeedbackError(ValueError):
    pass


def canonical_sector(raw: str, cfg: dict) -> str:
    low = (raw or "").lower().strip()
    for s in cfg["public_sectors"]:
        if s in low:
            return s
    return low or "unknown"


def company_sector(company: str, cfg: dict, apps_dir: Path = APPS) -> str:
    p = apps_dir / f"{company}.json"
    raw = json.loads(p.read_text())["form_fields"].get("sector_selected", {}).get("value", "") if p.exists() else ""
    return canonical_sector(raw, cfg)


def model_score(company: str, criterion: str, scores_dir: Path = SCORES) -> int:
    p = scores_dir / f"{company}.json"
    if not p.exists():
        raise FeedbackError(f"no score card for {company}")
    return json.loads(p.read_text())["criteria"][criterion]["final"]


def add_correction(conn: sqlite3.Connection, company: str, criterion: str, human_score: int, reason: str,
                   corrected_by: str, cfg: Optional[dict] = None, scores_dir: Path = SCORES,
                   apps_dir: Path = APPS, scope: str = "general") -> int:
    """scope 'this_case' marks an exception for this company only: it is logged and counted, never reused."""
    cfg = cfg or config.load()
    if criterion not in cfg["criteria"]:
        raise FeedbackError(f"unknown criterion {criterion}")
    if not isinstance(human_score, int) or not 0 <= human_score <= 5:
        raise FeedbackError("human score must be an integer 0-5")
    reason = reason.strip()
    if not reason or "\n" in reason or len(reason) > 200:
        raise FeedbackError("reason must be one line, at most 200 characters")
    if scope not in ("general", "this_case"):
        raise FeedbackError("scope must be 'general' or 'this_case'")
    ms = model_score(company, criterion, scores_dir)
    cur = conn.execute(
        "INSERT INTO corrections (company, sector, criterion, model_score, human_score, reason, corrected_by, scope) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (company, company_sector(company, cfg, apps_dir), criterion, ms, human_score, reason, corrected_by, scope))
    conn.commit()
    return cur.lastrowid


def _rows(conn: sqlite3.Connection, where: str = "", args=()) -> List[dict]:
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM corrections {where} ORDER BY corrected_at, id", args)]
    conn.row_factory = None
    return rows


def surface(conn: sqlite3.Connection, company: str, sector: str, criteria: Optional[List[str]] = None) -> Dict[str, List[dict]]:
    """Past corrections on other companies in the same sector, by criterion, ready to show on a card."""
    rows = _rows(conn, "WHERE sector = ? AND company <> ?", (sector, company))
    out: Dict[str, List[dict]] = {}
    for r in rows:
        if criteria and r["criterion"] not in criteria:
            continue
        r["message"] = (f"Last time on a similar company ({r['company']}, {r['sector']}) {r['corrected_by']} moved "
                        f"{r['criterion']} from {r['model_score']} to {r['human_score']} because {r['reason']}")
        out.setdefault(r["criterion"], []).append(r)
    return out


def flag(conn: sqlite3.Connection, target: str, target_id: int, kind: str, reason: str, by: str) -> int:
    """A named human marks a correction or email edit as a bad-day edit or retracts it. It is then never reused."""
    table = {"correction": "corrections", "email_edit": "email_edits"}.get(target)
    if not table or not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (target_id,)).fetchone():
        raise FeedbackError(f"no {target} with id {target_id}")
    cur = conn.execute("INSERT INTO feedback_flags (target, target_id, kind, reason, flagged_by) VALUES (?, ?, ?, ?, ?)",
                       (target, target_id, kind, reason.strip(), by))
    conn.commit()
    return cur.lastrowid


def flagged_ids(conn: sqlite3.Connection, target: str) -> set:
    return {r[0] for r in conn.execute("SELECT target_id FROM feedback_flags WHERE target=?", (target,))}


def usable_corrections(conn: sqlite3.Connection) -> List[dict]:
    """Corrections that may be reused: scope 'general' and not flagged as a bad day or retracted."""
    bad = flagged_ids(conn, "correction")
    return [r for r in _rows(conn) if r.get("scope", "general") == "general" and r["id"] not in bad]


def lessons(conn: sqlite3.Connection, company: str, cfg: Optional[dict] = None, apps_dir: Path = APPS) -> List[dict]:
    """Lessons for the scoring prompt (user 2026-11-24: only when 2+ agree).

    A lesson is a group of usable corrections on the same criterion, in the same direction, in this company's
    sector, from at least `feedback.inject_min_agreeing_companies` OTHER companies. Each keeps every reason, so
    the model sees why, not just what. Newest groups first, at most `feedback.inject_max_lessons`.
    """
    cfg = cfg or config.load()
    sector = company_sector(company, cfg, apps_dir)
    groups: Dict[tuple, List[dict]] = {}
    for r in usable_corrections(conn):
        if r["company"] != company and r["sector"] == sector:
            groups.setdefault((r["criterion"], _direction(r)), []).append(r)
    out = []
    for (crit, d), rs in groups.items():
        cos = sorted({r["company"] for r in rs})
        if len(cos) >= cfg["feedback"]["inject_min_agreeing_companies"]:
            out.append({"criterion": crit, "direction": d, "sector": sector, "companies": cos,
                        "moves": [f"{r['model_score']}->{r['human_score']}" for r in rs],
                        "reasons": [f"{r['company']}: {r['reason']} ({r['corrected_by']}, {r['corrected_at'][:10]})" for r in rs],
                        "latest": max(r["corrected_at"] for r in rs), "correction_ids": [r["id"] for r in rs]})
    out.sort(key=lambda x: x["latest"], reverse=True)
    return out[:cfg["feedback"]["inject_max_lessons"]]


def _direction(r: dict) -> str:
    return "up" if r["human_score"] > r["model_score"] else "down"


def similar_groups(conn: sqlite3.Connection, cfg: dict) -> List[dict]:
    """Groups of corrections with the same criterion and direction across >= N distinct companies."""
    n = cfg["feedback"]["min_similar_corrections"]
    groups: Dict[tuple, List[dict]] = {}
    for r in _rows(conn):
        groups.setdefault((r["criterion"], _direction(r)), []).append(r)
    out = []
    for (crit, d), rs in groups.items():
        companies = {r["company"] for r in rs}
        if len(companies) >= n:
            out.append({"criterion": crit, "direction": d, "corrections": rs, "companies": sorted(companies)})
    return out


def candidate_diff(cfg_text: str, cfg: dict, criterion: str, direction: str) -> Optional[str]:
    """Move `criterion` by proposal_step, offset against the largest other criterion in its group.
    Returns a unified diff, or None if the move would break the config rules."""
    group = next(g for g, ks in cfg["groups"].items() if criterion in ks)
    others = [k for k in cfg["groups"][group] if k != criterion]
    if not others:
        return None
    offset = max(others, key=lambda k: cfg["criteria"][k]["weight"])
    new = None
    for step in sorted({cfg["feedback"]["proposal_step"], 2, 1}, reverse=True):   # shrink until valid
        if step > cfg["feedback"]["proposal_step"]:
            continue
        delta = step if direction == "up" else -step
        cand = {criterion: cfg["criteria"][criterion]["weight"] + delta, offset: cfg["criteria"][offset]["weight"] - delta}
        if all(v > 0 for v in cand.values()):
            new = cand
            break
    if new is None:
        return None
    text = cfg_text
    for k, w in new.items():
        inline = re.compile(rf"^(  {k}: \{{name: \"[^\"]*\", weight: )(\d+)(\}})", re.M)
        block = re.compile(rf"(^  {k}:\n(?:    .*\n)*?    weight: )(\d+)", re.M)
        if inline.search(text):
            text = inline.sub(lambda m: f"{m.group(1)}{w}{m.group(3)}", text, count=1)
        elif block.search(text):
            text = block.sub(lambda m: f"{m.group(1)}{w}", text, count=1)
        else:
            return None
    config.validate(yaml.safe_load(text))   # raises if the proposal would be an invalid rubric
    return "".join(difflib.unified_diff(cfg_text.splitlines(True), text.splitlines(True),
                                        "config/rubric.yaml (current)", "config/rubric.yaml (proposed)"))


def propose(conn: sqlite3.Connection, cfg: Optional[dict] = None, cfg_path: Path = CONFIG_PATH) -> List[dict]:
    """Record a proposal for each qualifying group not already proposed with the same corrections."""
    cfg = cfg or config.load(cfg_path)
    cfg_text = cfg_path.read_text()
    made = []
    for g in similar_groups(conn, cfg):
        ids = ",".join(str(r["id"]) for r in g["corrections"])
        if conn.execute("SELECT 1 FROM weight_proposals WHERE criterion=? AND direction=? AND correction_ids=?",
                        (g["criterion"], g["direction"], ids)).fetchone():
            continue
        diff = candidate_diff(cfg_text, cfg, g["criterion"], g["direction"])
        if diff is None:
            diff = ("# No valid in-group weight move: it would take another criterion in the group to 0 or below.\n"
                    "# Discuss the anchor or scoring prompt for this criterion instead.\n")
        note = (f"# {len(g['corrections'])} corrections moved {g['criterion']} {g['direction']} across "
                f"{', '.join(g['companies'])}.\n# Candidate only: consistent corrections may mean the anchor or "
                f"scoring prompt is wrong rather than the weight. A human decides; code never applies this.\n")
        pid = conn.execute("INSERT INTO weight_proposals (criterion, direction, correction_ids, diff) VALUES (?, ?, ?, ?)",
                           (g["criterion"], g["direction"], ids, note + diff)).lastrowid
        made.append({"id": pid, **g, "diff": note + diff})
    conn.commit()
    return made


if __name__ == "__main__":
    a = sys.argv[1:]
    conn = db.connect()
    cfg = config.load()
    if a[:1] == ["add"] and len(a) in (6, 7):
        print("correction", add_correction(conn, a[1], a[2], int(a[3]), a[4], a[5], cfg,
                                           scope="this_case" if "--this-case" in a else "general"))
    elif a[:1] == ["flag"] and len(a) == 6:
        print("flag", flag(conn, a[1], int(a[2]), a[3], a[4], a[5]))
    elif a[:1] == ["lessons"] and len(a) == 2:
        print(json.dumps(lessons(conn, a[1], cfg), indent=1))
    elif a[:1] == ["list"]:
        for r in _rows(conn):
            print(f"{r['id']:3} {r['corrected_at']} {r['company']:11} {r['sector']:15} {r['criterion']} "
                  f"{r['model_score']}->{r['human_score']} by {r['corrected_by']}: {r['reason']}")
    elif a[:1] == ["surface"] and len(a) == 2:
        for crit, rs in surface(conn, a[1], company_sector(a[1], cfg)).items():
            for r in rs:
                print(r["message"])
    elif a[:1] == ["propose"]:
        for p in propose(conn, cfg):
            print(f"proposal {p['id']}:\n{p['diff']}")
    else:
        print(__doc__)
