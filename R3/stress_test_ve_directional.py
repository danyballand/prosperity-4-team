"""
Stress-test configs VE directional sous after_queue + haircut.

Vérifie que le gain +12k à +18k tient sous :
  S1 optimistic (h=0%, no after_queue)
  S2 realistic (h=25%, after_queue)
  S3 pessimistic (h=50%, after_queue)

Si le gain s'effondre en S2/S3 → c'est un artefact du modèle de fill trop optimiste.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate
from stress_test_haircut import _patched_apply_passive_fills, _RAW_APPLY

PP = tm.PRODUCT_PARAMS
BASE_VE = dict(PP["VELVETFRUIT_EXTRACT"])

import stress_test_haircut as sth


def set_ve(**kwargs):
    PP["VELVETFRUIT_EXTRACT"].clear()
    PP["VELVETFRUIT_EXTRACT"].update(BASE_VE)
    for k, v in kwargs.items():
        PP["VELVETFRUIT_EXTRACT"][k] = v


def run_cfg(label, ve_cfg, scenarios):
    set_ve(**ve_cfg)
    row = f"{label:<40s}"
    for (haircut, after_queue) in scenarios:
        sth._HAIRCUT = haircut
        sth._AFTER_QUEUE = after_queue
        lb.apply_passive_fills = _patched_apply_passive_fills
        try:
            total_ve = 0
            total_all = 0
            for d in (0, 1, 2):
                pnl = simulate(d)
                total_ve += pnl.get("VELVETFRUIT_EXTRACT", 0.0)
                total_all += sum(pnl.values())
        finally:
            lb.apply_passive_fills = _RAW_APPLY
        row += f"  VE={total_ve:>+6.0f} ALL={total_all:>+7.0f}"
    print(row, flush=True)


scenarios = [(0.0, False), (0.25, True), (0.50, True)]
headers = ["S1 opt (h=0)", "S2 real (h=25, queue)", "S3 pess (h=50, queue)"]

print("=" * 120)
print("Stress-test VE directional configs — VE PnL + ALL 3d PnL sous 3 scénarios")
print("=" * 120)
header = f"{'Config':<40s}  " + "  ".join(f"{h:<25s}" for h in headers)
print(header)
print("-" * 120)

configs = [
    ("A baseline (current, skew=0.05)", {}),
    ("G no clear + no skew (limit=200)", dict(inventory_clearing=False, skew_ticks_per_unit=0.0)),
    ("L full passive long-bias 300", dict(inventory_clearing=False, skew_ticks_per_unit=0.0,
                                          inventory_aware_take=False, position_limit=300)),
    ("F skew=0 only", dict(skew_ticks_per_unit=0.0)),
    ("E skew=0.02", dict(skew_ticks_per_unit=0.02)),
    ("G+half-skew (0.02 + no clear)", dict(inventory_clearing=False, skew_ticks_per_unit=0.02)),
]

for label, ve_cfg in configs:
    run_cfg(label, ve_cfg, scenarios)

print()
print("=" * 120)
print("Analyse :")
print("  Si le gain des configs G/L tient sous S3 → signal réel (pas artefact)")
print("  Si le gain s'effondre sous S3 → la construction de position repose sur same-price passive fills")
print("=" * 120)
