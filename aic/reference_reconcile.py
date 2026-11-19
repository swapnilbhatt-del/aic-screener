"""Compare reference/aic_arithmetic_checks.py (the user's draft) with Stage 2 checks.

The reference script is executed unchanged (stdout suppressed) and each of its rows is mapped to a Stage 2
check id. Output: agreement table, reclassifications, and Stage 2 checks the reference did not have.
"""
import contextlib
import io
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "reference" / "aic_arithmetic_checks.py"
CHECKS = ROOT / "data" / "checks"

# (company, reference label) -> Stage 2 check id
MAP = {
    **{(co, f"{t} (INR Cr)"): f"market.{t.lower()}" for co in
       ("CareCorner", "StockSathi", "Settlr", "GrainKind", "Pumpwise", "Talkbook") for t in ("TAM", "SAM", "SOM")},
    ("EarnWise", "TAM (INR Cr)"): "market.tam",
    ("Talkbook", "MRR (INR lakh) from seats x price"): "mrr_seats_deck",
    ("Talkbook", "MRR (INR lakh) form says 1.9"): "mrr_seats_form",
    ("Talkbook", "ARPU per team (INR/month)"): "arpu_from_seats",
    ("CAPilot", "Paying firms: deck 31 vs form 24 paying (+7 trial)"): "xdoc.customers_paying",
    ("CAPilot", "ARR (INR lakh) from MRR"): "arr_from_mrr",
    ("StockSathi", "CAC Oct (INR) deck calc vs form 'under 2,000'"): "xdoc.cac_inr",
    ("RentRoute", "Gross fee (INR lakh) 1.8% x 6.1 Cr"): "gross_fee",
    ("RentRoute", "Net fee (INR lakh) after 0.9% partner"): "net_fee",
    ("EarnWise", "Observed advance per worker per month vs TAM 12,000"): "advance_per_worker_vs_tam",
    ("GrainKind", "Blended CAC from channel mix vs stated 340"): "blended_cac_from_channels",
    ("Pumpwise", "TAM (INR Cr) at observed 23 sensors/firm"): "tam_at_observed_sensors",
    ("Pumpwise", "CAC per paid customer (INR) 4.4L/6"): "cac",
    ("Settlr", "Annual volume per SME (Cr) observed vs TAM assumption 4.5"): "volume_per_sme_vs_tam",
    ("Settlr", "CAC payback (months) recomputed vs stated 7"): "payback",
    ("Yatrika", "Revenue (INR lakh) 12% of 38.6 L"): "revenue_commission",
}


def reference_rows():
    with contextlib.redirect_stdout(io.StringIO()):
        ns = runpy.run_path(str(REF))
    return ns["checks"]


def reconcile():
    ours = {}
    for p in CHECKS.glob("*.json"):
        if p.name == "summary.json":
            continue
        for c in json.loads(p.read_text()):
            ours[(c["company"], c["id"])] = c
    rows, mapped = [], set()
    for co, label, stated, recomputed, unit, status in reference_rows():
        cid = MAP.get((co, label))
        mine = ours.get((co, cid)) if cid else None
        if mine:
            mapped.add((co, cid))
        rows.append({"company": co, "reference_label": label, "reference_status": status,
                     "reference_stated": stated, "reference_recomputed": recomputed, "stage2_id": cid,
                     "stage2_status": mine["status"] if mine else "NOT MAPPED",
                     "stage2_kind": mine["kind"] if mine else None,
                     "agree": bool(mine) and mine["status"] == status})
    extra = sorted(k for k in ours if k not in mapped)
    return rows, extra, ours


if __name__ == "__main__":
    rows, extra, ours = reconcile()
    for r in rows:
        print(f"{r['company']:11} {r['reference_status']:4} -> {r['stage2_status']:11} {r['stage2_kind'] or '':24} "
              f"{'' if r['agree'] else 'DIFFERS'} {r['reference_label'][:60]}")
    print(f"\n{len(rows)} reference checks, {sum(r['agree'] for r in rows)} agree, "
          f"{sum(not r['agree'] for r in rows)} differ; {len(extra)} Stage 2 checks not in the reference "
          f"({sum(ours[k]['status'] == 'FAIL' for k in extra)} of them FAIL)")
