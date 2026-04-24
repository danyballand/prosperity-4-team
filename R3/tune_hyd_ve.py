"""
Grid search paramétrique HYD + VE pour R3.

Phase 1 — HYD make_edge : balayage {80, 85, 90, 97, 105, 110, 120}
Phase 2 — VE make_edge × use_microprice × fixed_fv : grid sur la meilleure HYD

Baseline v2 : +23,929.5 SS (HYD edge=97, VE edge=3, microprice=True, fv=None)

Usage : python3 tune_hyd_ve.py
"""
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Import trader + backtest modules (trader_r3 sera mutable via PRODUCT_PARAMS)
import trader_r3 as trader_module
from local_backtest_r3 import simulate, PRODUCTS, DAYS

PRODUCT_PARAMS = trader_module.PRODUCT_PARAMS


def run_backtest(label):
    """Execute backtest 3 jours, retourne (total, pnl_per_product)."""
    total_per_product = defaultdict(float)
    for day in DAYS:
        pnl = simulate(day)
        for p in PRODUCTS:
            total_per_product[p] += pnl[p]
    total = sum(total_per_product.values())
    return total, dict(total_per_product)


def set_hyd(make_edge):
    PRODUCT_PARAMS["HYDROGEL_PACK"]["make_edge"] = make_edge


def set_ve(make_edge, use_microprice, fixed_fv):
    PRODUCT_PARAMS["VELVETFRUIT_EXTRACT"]["make_edge"] = make_edge
    PRODUCT_PARAMS["VELVETFRUIT_EXTRACT"]["use_microprice"] = use_microprice
    PRODUCT_PARAMS["VELVETFRUIT_EXTRACT"]["fixed_fv"] = fixed_fv


# ==============================================================
# Phase 1 — HYD make_edge (VE fixed v2)
# ==============================================================
print("=" * 70)
print("PHASE 1 — HYD make_edge grid  (VE: edge=3, microprice=True, fv=None)")
print("=" * 70)
# Reset VE config to v2 baseline
set_ve(make_edge=3, use_microprice=True, fixed_fv=None)

hyd_grid = [80, 85, 90, 95, 97, 100, 105, 110, 115, 120]
hyd_results = []

for edge in hyd_grid:
    set_hyd(edge)
    t0 = time.time()
    total, per_prod = run_backtest(f"HYD_edge={edge}")
    elapsed = time.time() - t0
    hyd_pnl = per_prod["HYDROGEL_PACK"]
    ve_pnl = per_prod["VELVETFRUIT_EXTRACT"]
    others_pnl = total - hyd_pnl - ve_pnl
    hyd_results.append((edge, total, hyd_pnl, ve_pnl, others_pnl))
    print(f"  edge={edge:3d}  TOTAL={total:+8.0f}  HYD={hyd_pnl:+7.0f}  "
          f"VE={ve_pnl:+6.0f}  OTHER={others_pnl:+6.0f}  ({elapsed:.1f}s)")

best_hyd = max(hyd_results, key=lambda r: r[1])
print(f"\n>> BEST HYD: edge={best_hyd[0]}  TOTAL={best_hyd[1]:+.0f}  "
      f"(HYD={best_hyd[2]:+.0f})")

# Lock best HYD
set_hyd(best_hyd[0])

# ==============================================================
# Phase 2 — VE config grid (HYD locked)
# ==============================================================
print()
print("=" * 70)
print(f"PHASE 2 — VE grid  (HYD locked edge={best_hyd[0]})")
print("=" * 70)

ve_grid = [
    # (make_edge, use_microprice, fixed_fv, label)
    (2, True,  None, "edge=2 micro=T fv=None"),
    (3, True,  None, "edge=3 micro=T fv=None  [v2 baseline]"),
    (4, True,  None, "edge=4 micro=T fv=None"),
    (5, True,  None, "edge=5 micro=T fv=None"),
    (2, False, None, "edge=2 micro=F fv=None"),
    (3, False, None, "edge=3 micro=F fv=None"),
    (4, False, None, "edge=4 micro=F fv=None"),
    (5, False, None, "edge=5 micro=F fv=None"),
]
ve_results = []

for (edge, microprice, fv, label) in ve_grid:
    set_ve(edge, microprice, fv)
    t0 = time.time()
    total, per_prod = run_backtest(label)
    elapsed = time.time() - t0
    hyd_pnl = per_prod["HYDROGEL_PACK"]
    ve_pnl = per_prod["VELVETFRUIT_EXTRACT"]
    others_pnl = total - hyd_pnl - ve_pnl
    ve_results.append((edge, microprice, fv, total, hyd_pnl, ve_pnl, others_pnl, label))
    print(f"  {label:<35s}  TOTAL={total:+8.0f}  VE={ve_pnl:+6.0f}  "
          f"HYD={hyd_pnl:+7.0f}  ({elapsed:.1f}s)")

best_ve = max(ve_results, key=lambda r: r[3])
print(f"\n>> BEST VE: {best_ve[7]}  TOTAL={best_ve[3]:+.0f}")

# ==============================================================
# Résumé final
# ==============================================================
print()
print("=" * 70)
print("RÉSUMÉ — best combo trouvée")
print("=" * 70)
print(f"  HYD make_edge = {best_hyd[0]}")
print(f"  VE  config    = {best_ve[7]}")
print(f"  TOTAL backtest = {best_ve[3]:+.0f} SS")
print(f"  vs baseline v2 = +23,929.5 SS")
print(f"  DELTA          = {best_ve[3] - 23929.5:+.0f} SS")
