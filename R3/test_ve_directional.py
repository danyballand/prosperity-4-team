"""
Test : désactiver inventory_clearing sur VE pour capturer les trends intraday.

Day 0 : -6 dir change  (flat)
Day 1 : +20.5 dir change (upward trend)
Day 2 : +28 dir change (strong upward trend)

Si MM agressive clearing nous sort des longs quand ça tente d'un trend,
on perd le paper profit. On teste 4 variants :
  A) baseline (inventory_clearing=True)
  B) no clearing (inventory_clearing=False)
  C) higher clearing_threshold (0.50 au lieu de 0.25)
  D) directional skew : skew_ticks_per_unit plus petit pour laisser inventory

+ une version buy&hold pur comme borne sup théorique.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_VE = dict(PP["VELVETFRUIT_EXTRACT"])


def set_ve(**kwargs):
    PP["VELVETFRUIT_EXTRACT"].clear()
    PP["VELVETFRUIT_EXTRACT"].update(BASE_VE)
    for k, v in kwargs.items():
        PP["VELVETFRUIT_EXTRACT"][k] = v


def eval_cfg(label, **cfg):
    set_ve(**cfg)
    daily_ve = {}
    total_ve = 0
    total_all = 0
    for d in (0, 1, 2):
        pnl = simulate(d)
        ve = pnl.get("VELVETFRUIT_EXTRACT", 0.0)
        daily_ve[d] = ve
        total_ve += ve
        total_all += sum(pnl.values())
    print(f"{label:<40s}  d0={daily_ve[0]:+6.0f}  d1={daily_ve[1]:+6.0f}  d2={daily_ve[2]:+6.0f}  ve3d={total_ve:+7.0f}  all3d={total_all:+8.0f}")
    return total_ve, total_all


print("=" * 100)
print("VE tuning : inventory_clearing vs laisser trends porter")
print("=" * 100)
print(f"{'Config':<40s}  {'d0':>6s}  {'d1':>6s}  {'d2':>6s}  {'VE 3d':>7s}  {'ALL 3d':>8s}")
print("-" * 100)

# baseline
eval_cfg("A) baseline (current)")

# no clearing
eval_cfg("B) no inventory_clearing", inventory_clearing=False)

# high clearing threshold 0.50
eval_cfg("C) clearing_thresh=0.50", clearing_threshold=0.50)

# very high clearing threshold 0.80 (almost never clears)
eval_cfg("D) clearing_thresh=0.80", clearing_threshold=0.80)

# small skew (laisse position se construire)
eval_cfg("E) skew 0.02 (vs 0.05)", skew_ticks_per_unit=0.02)

# no skew du tout
eval_cfg("F) skew=0", skew_ticks_per_unit=0.0)

# no clearing + no skew
eval_cfg("G) no clear + no skew", inventory_clearing=False, skew_ticks_per_unit=0.0)

# lower take_width (agressif entry)
eval_cfg("H) disable_take_true", disable_take=True)

# no clearing + limit 300
eval_cfg("I) no clear + limit=300", inventory_clearing=False, position_limit=300)

# plus large make_edge (capturer moins de ticks mais plus grosse size)
eval_cfg("J) make_edge=5", make_edge=5)

# inventory_aware_take off
eval_cfg("K) no inventory_aware_take", inventory_aware_take=False)

# combo : no clear + no skew + no inventory_aware_take + limit 300
eval_cfg("L) full passive long-bias", inventory_clearing=False, skew_ticks_per_unit=0.0,
        inventory_aware_take=False, position_limit=300)

print()
print("=" * 100)
print("Note : un buy&hold day 1 long 200 = +4,100  day 2 long 200 = +5,600  total borne = +9,700")
print("=" * 100)
