"""
Deep check config G (adaptive blend=0.5 clip=10) :
  - PnL par jour individuellement (détecte overfit single-day)
  - Sensibilité autour du point optimal (blend, clip)
  - HYD per-day detail
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_HYD = dict(PP["HYDROGEL_PACK"])


def set_hyd(**kwargs):
    PP["HYDROGEL_PACK"].clear()
    PP["HYDROGEL_PACK"].update(BASE_HYD)
    for k, v in kwargs.items():
        PP["HYDROGEL_PACK"][k] = v


def bt_all_days():
    per_day_total = {}
    per_day_hyd = {}
    for d in (0, 1, 2):
        pnl = simulate(d)
        per_day_total[d] = sum(pnl.values())
        per_day_hyd[d] = pnl.get("HYDROGEL_PACK", 0.0)
    return per_day_total, per_day_hyd


# === Grid sensibilité blend × clip ===
print("=" * 90)
print("Sensibilité adaptive FV (blend × clip) — PnL total 3 jours")
print("=" * 90)
print(f"{'blend \\ clip':>12s}  " + "  ".join(f"clip={c:>4.1f}" for c in [3, 5, 10, 15, 20]))
for blend in [0.25, 0.50, 0.75, 1.00]:
    row = f"{blend:>12.2f}  "
    for clip in [3, 5, 10, 15, 20]:
        set_hyd(fixed_fv=10000, adaptive_fixed_fv=True,
                fixed_fv_book_blend=blend, fixed_fv_book_clip=float(clip),
                make_edge=97)
        pd_total, _ = bt_all_days()
        total = sum(pd_total.values())
        row += f"  {total:>+8.0f}"
    print(row)

print()

# === Per-day stability pour G (0.5, 10) ===
print("=" * 90)
print("Per-day stability : config G (blend=0.5, clip=10)")
print("=" * 90)
set_hyd(fixed_fv=10000, adaptive_fixed_fv=True,
        fixed_fv_book_blend=0.50, fixed_fv_book_clip=10.0,
        make_edge=97)
pd_total, pd_hyd = bt_all_days()
print(f"{'Day':>5s}  {'Total':>10s}  {'HYD':>10s}  {'non-HYD':>10s}")
for d in (0, 1, 2):
    print(f"  {d:>3d}  {pd_total[d]:>+10.0f}  {pd_hyd[d]:>+10.0f}  {pd_total[d]-pd_hyd[d]:>+10.0f}")
print(f" Total  {sum(pd_total.values()):>+10.0f}  {sum(pd_hyd.values()):>+10.0f}  {sum(pd_total.values())-sum(pd_hyd.values()):>+10.0f}")

print()

# === Baseline comparison ===
print("=" * 90)
print("Baseline (A) per-day :")
print("=" * 90)
set_hyd(fixed_fv=10000, adaptive_fixed_fv=False, make_edge=97)
pd_total, pd_hyd = bt_all_days()
for d in (0, 1, 2):
    print(f"  {d:>3d}  {pd_total[d]:>+10.0f}  {pd_hyd[d]:>+10.0f}  {pd_total[d]-pd_hyd[d]:>+10.0f}")
print(f" Total  {sum(pd_total.values()):>+10.0f}  {sum(pd_hyd.values()):>+10.0f}  {sum(pd_total.values())-sum(pd_hyd.values()):>+10.0f}")
