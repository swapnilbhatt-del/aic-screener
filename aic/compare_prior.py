"""Compare Stage 4 scores with reference/AIC_scores_v1.csv (the user's prior scores, treated as a hypothesis)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIOR = ROOT / "reference" / "AIC_scores_v1.csv"
COLS = {"F1": "F1_depth", "F2": "F2_owns_risk", "F3": "F3_candour", "F4": "F4_team", "T1": "T1_traction",
        "T2": "T2_unit_econ", "T3": "T3_path", "M1": "M1_market", "M2": "M2_defensibility", "M3": "M3_thesis",
        "S1": "S1_capital", "S2": "S2_integrity"}
BAND = {"call": "call", "partner": "partner_review", "pass": "pass", "hold": "hold"}


def prior_band(s: str) -> str:
    s = s.lower()
    for k, v in BAND.items():
        if s.startswith(k):
            return v
    return s


def compare():
    rows = []
    for p in csv.DictReader(PRIOR.open()):
        f = ROOT / "data" / "scores" / f"{p['company']}.json"
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        diffs = {k: (int(p[c]), r["criteria"][k]["final"]) for k, c in COLS.items() if int(p[c]) != r["criteria"][k]["final"]}
        rows.append({"company": p["company"], "prior_total": float(p["total"]), "new_total": r["total"],
                     "prior_band": prior_band(p["band"]), "new_band": r["band"],
                     "band_agrees": prior_band(p["band"]) == r["band"],
                     "criteria_changed": diffs, "n_changed": len(diffs),
                     "largest_moves": sorted(diffs.items(), key=lambda kv: -abs(kv[1][0] - kv[1][1]))[:4]})
    return rows


if __name__ == "__main__":
    for r in compare():
        moves = ", ".join(f"{k} {a}->{b}" for k, (a, b) in r["largest_moves"])
        print(f"{r['company']:11} prior {r['prior_total']:5.1f} {r['prior_band']:15} new {r['new_total']:5.1f} "
              f"{r['new_band']:15} {'same band' if r['band_agrees'] else 'BAND DIFFERS'}  changed={r['n_changed']:2}  {moves}")
