"""
v7-micro : activer UN strike à la fois avec smile FV + limits variés pour
isoler l'effet adverse selection vs biais smile exploitable.

Si un strike donne gain net → c'est tradable.
Si tous perdent → le problème est structurel (adverse selection sans delta hedge).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate
from stress_test_v7 import _patched_apply_passive_fills, _RAW_APPLY

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}


def reset():
    PP.clear()
    for k, v in BASE_PP.items():
        PP[k] = dict(v)


def run(label, strike, limit, edge):
    reset()
    import stress_test_v7 as s7
    s7._HAIRCUT = 0.25
    s7._AFTER_QUEUE = True
    if strike is not None:
        sym = f"VEV_{strike}"
        PP[sym]["position_limit"] = limit
        PP[sym]["use_smile_fv"] = True
        PP[sym]["make_edge"] = edge
        PP[sym]["inventory_clearing"] = True
        PP[sym]["clearing_threshold"] = 0.30
        PP[sym]["min_wall_volume"] = 3
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        total = 0
        by_prod = {}
        for d in (0, 1, 2):
            pnl = simulate(d)
            total += sum(pnl.values())
            for k, v in pnl.items():
                by_prod[k] = by_prod.get(k, 0) + v
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return total, by_prod


print("=" * 90)
print("v7-micro : 1 strike à la fois, sous S2 real (h=25%, queue)")
print("=" * 90)

# Baseline
total_base, by_prod_base = run("baseline v6", None, 0, 0)
print(f"  v6 baseline                     TOTAL={total_base:+.0f}")
print()

# Test chaque strike disabled avec smile FV à différents limits
configs = [
    # (strike, limit, edge)
    (5400, 30, 3),   # LONG bias (biais -0.014)
    (5400, 50, 3),
    (5400, 100, 2),
    (6000, 30, 3),   # SHORT bias (biais +0.014)
    (6000, 50, 3),
    (6000, 100, 2),
    (5200, 50, 3),
    (5300, 50, 3),
    (5500, 50, 3),
    (6500, 30, 3),
    # Activer 4500 en smile FV (biais massif +0.049, déjà actif en MM)
    (4500, 300, 3),  # trader déjà a 300 actif
]

for (strike, limit, edge) in configs:
    total, by_prod = run(f"VEV_{strike} L={limit} E={edge}", strike, limit, edge)
    delta = total - total_base
    vev_pnl = by_prod.get(f"VEV_{strike}", 0) - by_prod_base.get(f"VEV_{strike}", 0)
    print(f"  VEV_{strike} L={limit:>3d} E={edge}  TOTAL={total:+.0f}  "
          f"Δvs_v6={delta:+.0f}  ΔVEV_{strike}={vev_pnl:+.0f}")

print()
print("=" * 90)
print("Interprétation :")
print("  Δ > 0  → strike tradable en smile FV seul (capture biais)")
print("  Δ < 0  → adverse selection dominante, smile FV insuffisant")
print("=" * 90)
