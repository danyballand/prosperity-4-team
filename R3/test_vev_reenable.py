"""
Test rapide : réactiver VEV 5200-6500 avec le MM actuel (sans BS pricing).
Mesure l'adverse selection réelle avec les nouveaux limits (300) et params.

Utile pour décider si on a besoin du module BS complet, ou si un simple
edge adaptatif suffit.
"""
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as trader_module
from local_backtest_r3 import simulate, PRODUCTS, DAYS

PRODUCT_PARAMS = trader_module.PRODUCT_PARAMS


def run_backtest():
    total_per_product = defaultdict(float)
    for day in DAYS:
        pnl = simulate(day)
        for p in PRODUCTS:
            total_per_product[p] += pnl[p]
    total = sum(total_per_product.values())
    return total, dict(total_per_product)


def config_vev(strike, limit, edge):
    sym = f"VEV_{strike}"
    PRODUCT_PARAMS[sym]["position_limit"] = limit
    PRODUCT_PARAMS[sym]["make_edge"] = edge


# Test scenarios — cap progressif pour voir le breakeven
scenarios = [
    # (label, config)
    ("baseline (all disabled)", []),
    ("V5400 limit=30 edge=2",  [(5400, 30, 2)]),
    ("V5400 limit=30 edge=5",  [(5400, 30, 5)]),
    ("V5400 limit=50 edge=5",  [(5400, 50, 5)]),
    ("V5400 limit=100 edge=5", [(5400, 100, 5)]),
    ("V5400 limit=300 edge=5", [(5400, 300, 5)]),
    ("V5400 limit=100 edge=8", [(5400, 100, 8)]),
    ("V5400+V5500 limit=50 edge=5",  [(5400, 50, 5), (5500, 50, 5)]),
    ("All VEV 5200+ limit=50 edge=5", [(5200, 50, 5), (5300, 50, 5), (5400, 50, 5), (5500, 50, 5), (6000, 50, 5), (6500, 50, 5)]),
]

print("=" * 70)
print("TEST — réactivation VEV 5200+ (MM basique sans BS)")
print("=" * 70)
results = []
for (label, config) in scenarios:
    # reset : disable all
    for s in (5200, 5300, 5400, 5500, 6000, 6500):
        config_vev(s, 0, 1)
    for (strike, limit, edge) in config:
        config_vev(strike, limit, edge)
    total, pnl = run_backtest()
    v5400 = pnl.get("VEV_5400", 0)
    v5500 = pnl.get("VEV_5500", 0)
    v5200_6500 = sum(pnl.get(f"VEV_{s}", 0) for s in (5200, 5300, 5400, 5500, 6000, 6500))
    delta_vs_baseline = v5200_6500
    print(f"  {label:<45s}  TOTAL={total:+.0f}  VEV5200+={v5200_6500:+.0f}  "
          f"V5400={v5400:+.0f}  V5500={v5500:+.0f}")
    results.append((label, total, v5200_6500))

print()
best = max(results, key=lambda r: r[1])
print(f">> Best : {best[0]} → TOTAL {best[1]:+.0f} (VEV5200+ {best[2]:+.0f})")
