"""Stage 5: blind backtest against the 12 deal memos.

Blindness is enforced three ways:
 1. The scorer sees only data/memos/blind/ (decision, stage, source, rationale, names removed; IDs shuffled).
 2. vault(): every file that could reveal an outcome is moved outside the repo while the scorer runs.
 3. unseal(): decisions are read only if all 12 blind scores exist, validate, and their hashes are recorded
    in a manifest first. Any later edit to a score file is detected.

  python -m aic.backtest vault <dir>      move outcome-bearing files out (before scoring)
  python -m aic.backtest unvault <dir>    move them back (after scoring)
  python -m aic.backtest validate <ID>    validate one raw blind score
  python -m aic.backtest score            compute all blind scores and write the manifest
  python -m aic.backtest unseal           check manifest, then read decisions and analyse
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from . import config, scoring

ROOT = Path(__file__).resolve().parent.parent
BLIND = ROOT / "data" / "memos" / "blind"
SEALED = ROOT / "data" / "memos" / "sealed" / "decisions.json"
RAW = ROOT / "data" / "backtest" / "raw"
OUT = ROOT / "data" / "backtest" / "scores"
MANIFEST = ROOT / "data" / "backtest" / "scores_manifest.json"
RESULT = ROOT / "data" / "backtest" / "result.json"

# Files that reveal memo outcomes, directly or indirectly.
LEAKY = ["data/memos/sealed", "seed/memos", "seed/notes", "seed/curation", "data/text/memos.json",
         "data/text/notes.json", "data/notes.json", "reference/AIC_Rubric_v1.md", "reports",
         "data/research", "data/scores", "data/applications", "data/claims", "data/checks", "reference/AIC_scores_v1.csv"]


class SealError(RuntimeError):
    pass


def vault(dest: Path) -> List[str]:
    dest.mkdir(parents=True, exist_ok=True)
    moved = []
    for rel in LEAKY:
        src = ROOT / rel
        if src.exists():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(target))
            moved.append(rel)
    (dest / "VAULT.json").write_text(json.dumps({"moved": moved, "at": _now()}))
    return moved


def unvault(dest: Path) -> List[str]:
    moved = json.loads((dest / "VAULT.json").read_text())["moved"]
    for rel in moved:
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest / rel), str(target))
    return moved


def blind_memos() -> Dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(BLIND.glob("MEMO-*.json"))}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def score_all() -> Dict[str, dict]:
    """Score every blind memo in code from the raw proposals; write the manifest. Never reads decisions."""
    cfg = config.load()
    memos = blind_memos()
    missing = [m for m in memos if not (RAW / f"{m}.json").exists()]
    if missing:
        raise SealError(f"raw scores missing for {missing}")
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    for mid, memo in memos.items():
        raw = json.loads((RAW / f"{mid}.json").read_text())
        r = scoring.score(mid, raw=raw, cfg=cfg, memo=memo)
        (OUT / f"{mid}.json").write_text(json.dumps(r, indent=1, ensure_ascii=False))
        results[mid] = r
    MANIFEST.write_text(json.dumps({
        "scored_at": _now(), "n": len(results),
        "raw": {m: _sha(RAW / f"{m}.json") for m in results},
        "scores": {m: _sha(OUT / f"{m}.json") for m in results}}, indent=1))
    return results


def unseal() -> List[dict]:
    """Read sealed decisions only after every blind score is written and unchanged since the manifest."""
    if not MANIFEST.exists():
        raise SealError("no scores manifest: run 'score' first")
    man = json.loads(MANIFEST.read_text())
    memos = blind_memos()
    if set(man["scores"]) != set(memos) or len(memos) != 12:
        raise SealError("manifest does not cover all 12 blind memos")
    for m in memos:
        if _sha(OUT / f"{m}.json") != man["scores"][m] or _sha(RAW / f"{m}.json") != man["raw"][m]:
            raise SealError(f"{m}: score changed after the manifest was written")
    if not SEALED.exists():
        raise SealError("sealed decisions not present (still in the vault?)")
    man["unsealed_at"] = _now()
    MANIFEST.write_text(json.dumps(man, indent=1))
    return json.loads(SEALED.read_text())["memos"]


EXPECTED = {"INVESTED": "call", "PASSED": "pass"}


def outcome(decision: str, band: str) -> str:
    """agree / disagree / review (partner review: the rubric did not commit either way)."""
    if band == "partner_review":
        return "review"
    if decision == "INVESTED":
        return "agree" if band == "call" else "disagree"
    return "agree" if band in ("pass", "hold") else "disagree"


def sensitivity_band(r: dict, cfg: dict, drop: List[str]) -> dict:
    """Recompute the band with some criteria removed and the rest re-weighted to 100. A diagnostic only."""
    keep = {k: c for k, c in r["criteria"].items() if k not in drop}
    w = sum(c["weight"] for c in keep.values())
    total = sum(c["weight"] * c["final"] / 5 for c in keep.values()) * 100 / w
    gates = r["gates"]
    band, _ = scoring.band_for(total, gates, False, cfg)
    return {"total": round(total, 1), "band": band}


def _gate_state(gates: dict, g: str) -> str:
    """G2 in the memos covers both G2a (regulator) and G2b (capital): flagged if either is."""
    keys = ["G2a", "G2b"] if g == "G2" else [g]
    states = [gates[k]["state"] for k in keys if k in gates]
    return "flag" if "flag" in states else (states[0] if states else "n/a")


def analyse(decisions: List[dict]) -> dict:
    cfg = config.load()
    rows = []
    for d in decisions:
        r = json.loads((OUT / f"{d['anon_id']}.json").read_text())
        unknown = [k for k, c in r["criteria"].items() if c["unknown"]]
        deciding = [{"criterion": x["criterion"], "quote": x["quote"],
                     "model_score": r["criteria"][x["criterion"]]["final"] if x["criterion"] in r["criteria"] else None,
                     "model_gate": _gate_state(r["gates"], x["criterion"]) if x["criterion"].startswith("G") else None}
                    for x in d["deciding_criteria"]]
        rows.append({
            "memo_no": d["memo_no"], "company": d["company"], "anon_id": d["anon_id"], "decision": d["decision"],
            "total": r["total"], "band": r["band"], "result": outcome(d["decision"], r["band"]),
            "founder": r["founder_subtotal"], "path": r["path_subtotal"],
            "gates": {k: v["state"] for k, v in r["gates"].items()}, "unknown": unknown,
            "scores": {k: c["final"] for k, c in r["criteria"].items()}, "deciding": deciding,
            "adjustments": r["adjustments"],
            "sens_known_only": sensitivity_band(r, cfg, unknown),
            "sens_no_M3": sensitivity_band(r, cfg, ["M3"]),
            "sens_known_no_M3": sensitivity_band(r, cfg, sorted(set(unknown) | {"M3"})),
        })
    def rate(key):
        res = [outcome(x["decision"], x[key]["band"]) if key else x["result"] for x in rows]
        return {"agree": res.count("agree"), "disagree": res.count("disagree"), "review": res.count("review")}
    by_band = {}
    for x in rows:
        by_band.setdefault(x["band"], {"INVESTED": 0, "PASSED": 0})[x["decision"]] += 1
    out = {"rows": sorted(rows, key=lambda x: x["memo_no"]),
           "agreement": {"as_scored": rate(None), "unknowns_excluded": rate("sens_known_only"),
                         "M3_excluded": rate("sens_no_M3"), "unknowns_and_M3_excluded": rate("sens_known_no_M3")},
           "by_band": by_band, "config_version": cfg.get("version"),
           "note": "Sensitivities re-weight remaining criteria to 100; diagnostics only, not a rubric change."}
    RESULT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "vault":
        print("moved:", vault(Path(sys.argv[2])))
    elif cmd == "unvault":
        print("restored:", unvault(Path(sys.argv[2])))
    elif cmd == "validate":
        mid = sys.argv[2]
        memo = blind_memos()[mid]
        errs, _ = scoring.validate(json.loads((RAW / f"{mid}.json").read_text()), scoring.Sources(mid, memo), config.load())
        print(f"{mid}: {len(errs)} errors")
        for e in errs:
            print("  ", e)
        sys.exit(1 if errs else 0)
    elif cmd == "score":
        for m, r in score_all().items():
            print(f"{m} {r['total']:5.1f} {r['band']}")
    elif cmd == "unseal":
        res = analyse(unseal())
        for x in res["rows"]:
            print(f"memo {x['memo_no']:2} {x['company'][:20]:20} {x['decision']:8} {x['total']:5.1f} {x['band']:15} {x['result']}")
        print(json.dumps(res["agreement"], indent=1))
    else:
        print(__doc__)
