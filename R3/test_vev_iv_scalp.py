"""
Test IV-surface scalping VEV_5400 existant (flag ENABLE_VEV_5400_SCALPING).
Compare baseline (scalp OFF) vs scalp ON sur 3 jours.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS


def run_backtest(label):
    total_per_product = {}
    grand_total = 0
    for d in (0, 1, 2):
        pnl = simulate(d)
        for k, v in pnl.items():
            total_per_product[k] = total_per_product.get(k, 0) + v
            grand_total += v
    return grand_total, total_per_product


print("=" * 80)
print("Test IV-surface scalping VEV_5400 (module existant)")
print("=" * 80)

# Baseline : scalp OFF (état actuel)
tm.ENABLE_VEV_5400_SCALPING = False
# Disabled strikes déjà set sur 0 limit
for s in (5200, 5300, 5400, 5500, 6000, 6500):
    PP[f"VEV_{s}"]["position_limit"] = 0
total_off, by_prod_off = run_backtest("scalp OFF")
print(f"  scalp OFF   TOTAL={total_off:+.0f}  V5400={by_prod_off.get('VEV_5400', 0):+.0f}")

# Scalp ON (limit 300 requis)
tm.ENABLE_VEV_5400_SCALPING = True
PP["VEV_5400"]["position_limit"] = 300
total_on, by_prod_on = run_backtest("scalp ON")
print(f"  scalp ON    TOTAL={total_on:+.0f}  V5400={by_prod_on.get('VEV_5400', 0):+.0f}")

delta = total_on - total_off
print()
print(f"Δ IV-surface scalping V5400 : {delta:+.0f} SS")
print(f"  scalp gain sur V5400  : {by_prod_on.get('VEV_5400', 0) - by_prod_off.get('VEV_5400', 0):+.0f}")
print(f"  side-effect autres    : {delta - (by_prod_on.get('VEV_5400', 0) - by_prod_off.get('VEV_5400', 0)):+.0f}")
