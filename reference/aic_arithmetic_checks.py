"""
Deterministic arithmetic checks on each deck's own claims.
Units: everything converted to INR. 1 Cr = 1e7, 1 lakh Cr = 1e12.
Each check: (company, label, stated_in_deck, recomputed_from_deck_inputs, unit_note)
A check FAILs if the recomputed value differs from the stated value by more than 5%.
"""
CR = 1e7
LAKH_CR = 1e12

def to_cr(x_inr):
    return x_inr / CR

checks = []

def add(company, label, stated, recomputed, unit):
    diff = abs(recomputed - stated) / stated if stated else float("inf")
    status = "PASS" if diff <= 0.05 else "FAIL"
    checks.append((company, label, stated, round(recomputed, 2), unit, status))

# ---- Market sizing: formula = count x spend (per year) ----
# CareCorner
add("CareCorner", "TAM (INR Cr)", 114000, to_cr(190e6 * 6000), "Cr")
add("CareCorner", "SAM (INR Cr)", 5400, to_cr(9e6 * 6000), "Cr")
add("CareCorner", "SOM (INR Cr)", 35, to_cr(25 * 1.4e7), "Cr")
# StockSathi
add("StockSathi", "TAM (INR Cr)", 1728000, to_cr(12e6 * 1.2e5 * 12), "Cr")
add("StockSathi", "SAM (INR Cr)", 64800, to_cr(450e3 * 1.2e5 * 12), "Cr")
add("StockSathi", "SOM (INR Cr)", 518, to_cr(9000 * 48000 * 12), "Cr")
# Settlr  (2.1M SMEs x INR 4.5 Cr)
add("Settlr", "TAM (INR Cr)", 9.4e5, to_cr(2.1e6 * 4.5e7), "Cr")
add("Settlr", "SAM (INR Cr)", 1.8e5, to_cr(400e3 * 4.5e7), "Cr")
add("Settlr", "SOM (INR Cr)", 6750, to_cr(15000 * 4.5e7), "Cr")
# GrainKind
add("GrainKind", "TAM (INR Cr)", 91200, to_cr(38e6 * 2400), "Cr")
add("GrainKind", "SAM (INR Cr)", 14400, to_cr(6e6 * 2400), "Cr")
add("GrainKind", "SOM (INR Cr)", 28.8, to_cr(90000 * 3200), "Cr")
# EarnWise (10M workers x 12,000/month x 12)
add("EarnWise", "TAM (INR Cr)", 14400, to_cr(10e6 * 12000 * 12), "Cr")
# Pumpwise (300K x 60 sensors x 9,000)
add("Pumpwise", "TAM (INR Cr)", 16200, to_cr(300e3 * 60 * 9000), "Cr")
add("Pumpwise", "SAM (INR Cr)", 4536, to_cr(84e3 * 60 * 9000), "Cr")
add("Pumpwise", "SOM (INR Cr)", 21.6, to_cr(400 * 60 * 9000), "Cr")
# Talkbook
add("Talkbook", "TAM (INR Cr)", 4200, to_cr(7e6 * 6000), "Cr")
add("Talkbook", "SAM (INR Cr)", 660, to_cr(1.1e6 * 6000), "Cr")
add("Talkbook", "SOM (INR Cr)", 27, to_cr(45000 * 6000), "Cr")

# ---- Unit economics and traction ----
# Talkbook MRR: 340 paid seats x INR 500/month
add("Talkbook", "MRR (INR lakh) from seats x price", 2.1, 340 * 500 / 1e5, "lakh")
add("Talkbook", "MRR (INR lakh) form says 1.9", 1.9, 340 * 500 / 1e5, "lakh")
# Talkbook ARPU: deck says 13,000/team/month; seats/teams x price
add("Talkbook", "ARPU per team (INR/month)", 13000, (340 / 16) * 500, "INR")
# CAPilot paying firms: deck 31 vs form 24 paying + 7 trial
add("CAPilot", "Paying firms: deck 31 vs form 24 paying (+7 trial)", 31, 24, "firms")
# CAPilot ARR: MRR 78,000 x 12
add("CAPilot", "ARR (INR lakh) from MRR", 9.4, 78000 * 12 / 1e5, "lakh")
# StockSathi CAC: 40,000 field cost / 14 stores
add("StockSathi", "CAC Oct (INR) deck calc vs form 'under 2,000'", 2000, 40000 / 14, "INR")
# RentRoute fee: 1.8% of 6.1 Cr volume (gross), 0.9% partner cost
add("RentRoute", "Gross fee (INR lakh) 1.8% x 6.1 Cr", 11, 0.018 * 6.1e7 / 1e5, "lakh")
add("RentRoute", "Net fee (INR lakh) after 0.9% partner", 5.5, 0.009 * 6.1e7 / 1e5, "lakh")
# EarnWise: advances per enrolled worker over 4 months vs TAM assumption of 12,000/month
per_worker_total = 38e5 / 1600
add("EarnWise", "Observed advance per worker per month vs TAM 12,000", 12000, per_worker_total / 4, "INR")
# GrainKind: channel CAC weighted = blended?
blend = 0.45*410 + 0.25*290 + 0.20*210 + 0.10*380
add("GrainKind", "Blended CAC from channel mix vs stated 340", 340, blend, "INR")
# Pumpwise: TAM assumes 60 sensors/firm; observed average is 23
add("Pumpwise", "TAM (INR Cr) at observed 23 sensors/firm", 16200, to_cr(300e3 * 23 * 9000), "Cr")
# Pumpwise CAC: 11 pilots x 4.4 L / 6 paid
add("Pumpwise", "CAC per paid customer (INR) 4.4L/6", 73000, 4.4e5 / 6, "INR")
# Settlr: observed monthly volume per SME and implied annual
add("Settlr", "Annual volume per SME (Cr) observed vs TAM assumption 4.5", 4.5, 86 * 12 / 1150, "Cr")
# Settlr payback: CAC / (monthly fees x gross margin)
add("Settlr", "CAC payback (months) recomputed vs stated 7", 7, 14500 / (6800 * 0.58), "months")
# Yatrika revenue: 12% of 38.6 L
add("Yatrika", "Revenue (INR lakh) 12% of 38.6 L", 4.6, 0.12 * 38.6, "lakh")

print(f"{'Company':<12} {'Check':<62} {'Stated':>14} {'Recomputed':>14} {'Status'}")
print("-" * 112)
for c, l, s, r, u, st in checks:
    print(f"{c:<12} {l:<62} {s:>14,.2f} {r:>14,.2f} {st}  ({u})")
fails = [x for x in checks if x[5] == "FAIL"]
print(f"\n{len(checks)} checks, {len(fails)} FAIL")
