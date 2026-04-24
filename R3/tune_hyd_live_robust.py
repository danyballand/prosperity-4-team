"""
Grid test HYDROGEL_PACK : trouver une config robuste au "worst-case 100k"
exposé par le submit IMC 369298 (HYD -5,021 sur first 100k ts day 2).

Scénarios testés :
  A. Baseline actuel                 fixed_fv=10000, adaptive=OFF, make_edge=97
  B. Adaptive FV                     fixed_fv=10000, adaptive=ON (blend=0.5, clip=3), make_edge=97
  C. Pure wall_mid (comme VE)        fixed_fv=None, use_microprice=True, make_edge=3
  D. Wide edge                       fixed_fv=10000, adaptive=OFF, make_edge=150
  E. Adaptive FV blend=0.25 clip=5   (moins agressif)
  F. Adaptive FV blend=0.75 clip=5   (plus agressif)

Métriques :
  - Full 3 days backtest (notre référence)
  - Worst 100k segment : day 2 ts 0..100_000 (celui qui tue en live)
  - Pire jour seul : min(day0, day1, day2)
"""
import os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate, PRODUCTS

PP = tm.PRODUCT_PARAMS

# --- Snapshot baseline params ---
BASE_HYD = dict(PP["HYDROGEL_PACK"])


def reset_hyd():
    PP["HYDROGEL_PACK"].clear()
    PP["HYDROGEL_PACK"].update(BASE_HYD)


def set_hyd(**kwargs):
    reset_hyd()
    for k, v in kwargs.items():
        PP["HYDROGEL_PACK"][k] = v


def bt_full_3days():
    total = 0.0
    per_day = {}
    for d in (0, 1, 2):
        pnl = simulate(d)
        per_day[d] = (sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0.0))
        total += sum(pnl.values())
    return total, per_day


def bt_day2_first_100k():
    pnl = simulate(2, max_ts=100_000)
    return sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0.0)


SCENARIOS = [
    ("A. baseline (fv=10k fixe)",
     {"fixed_fv": 10000, "adaptive_fixed_fv": False, "make_edge": 97}),
    ("B. adaptive FV blend=0.5 clip=3",
     {"fixed_fv": 10000, "adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.50, "fixed_fv_book_clip": 3.0, "make_edge": 97}),
    ("C. pure wall_mid (no anchor)",
     {"fixed_fv": None, "use_microprice": True, "make_edge": 3}),
    ("D. wide edge 150",
     {"fixed_fv": 10000, "adaptive_fixed_fv": False, "make_edge": 150}),
    ("E. adaptive blend=0.25 clip=5",
     {"fixed_fv": 10000, "adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.25, "fixed_fv_book_clip": 5.0, "make_edge": 97}),
    ("F. adaptive blend=0.75 clip=5",
     {"fixed_fv": 10000, "adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.75, "fixed_fv_book_clip": 5.0, "make_edge": 97}),
    ("G. adaptive blend=0.5 clip=10 (large)",
     {"fixed_fv": 10000, "adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.50, "fixed_fv_book_clip": 10.0, "make_edge": 97}),
    ("H. adaptive blend=1.0 clip=5 (=book)",
     {"fixed_fv": 10000, "adaptive_fixed_fv": True, "fixed_fv_book_blend": 1.00, "fixed_fv_book_clip": 5.0, "make_edge": 97}),
]

print("=" * 90)
print("HYD grid search — live-robust config")
print("=" * 90)
print(f"{'Scenario':<40s}  {'3day total':>10s}  {'HYD 3d':>8s}  {'worst 100k':>10s}  {'HYD 100k':>9s}")
print("-" * 90)

results = []
for (label, cfg) in SCENARIOS:
    set_hyd(**cfg)
    total_3d, per_day = bt_full_3days()
    hyd_3d = sum(per_day[d][1] for d in (0, 1, 2))
    total_100k, hyd_100k = bt_day2_first_100k()
    print(f"{label:<40s}  {total_3d:>+10.0f}  {hyd_3d:>+8.0f}  {total_100k:>+10.0f}  {hyd_100k:>+9.0f}")
    results.append((label, cfg, total_3d, hyd_3d, total_100k, hyd_100k))

print("-" * 90)
print()
# Best par critère
best_3d = max(results, key=lambda r: r[2])
best_100k = max(results, key=lambda r: r[4])
best_both = max(results, key=lambda r: r[2] * 0.7 + r[4] * 0.3)  # trade-off

print(f"BEST full 3day total   : {best_3d[0]}  ({best_3d[2]:+.0f})")
print(f"BEST worst 100k (live) : {best_100k[0]}  ({best_100k[4]:+.0f})")
print(f"BEST trade-off 70/30   : {best_both[0]}  ({best_both[2]:+.0f} / {best_both[4]:+.0f})")
