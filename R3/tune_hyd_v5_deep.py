"""
Deep check V10 (clip=50 tw=2) :
  - Per-day stability (pas d'overfit single-day)
  - Sensibilité autour du point optimal (clip, tw)
  - Compare vs V1 (current v4)
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


# === Grid sensibilité clip × tw ===
print("=" * 100)
print("Sensibilité (clip × take_width) — HYD PnL 3 jours (cells = HYD 3d)")
print("=" * 100)
CLIPS = [10, 20, 30, 40, 50, 75, 100]
TWS = [0, 1, 2, 3, 4]
print(f"{'clip \\ tw':>10s}  " + "  ".join(f"tw={t:>2d}" for t in TWS))
for clip in CLIPS:
    row = f"{clip:>10.0f}  "
    for tw in TWS:
        set_hyd(fixed_fv=10000, adaptive_fixed_fv=True,
                fixed_fv_book_blend=0.50, fixed_fv_book_clip=float(clip),
                make_edge=97, take_width=tw, position_limit=200)
        _, pd_hyd = bt_all_days()
        print_val = sum(pd_hyd.values())
        row += f"  {print_val:>+8.0f}"
    print(row)
print()

# === Per-day stability V10 (clip=50 tw=2) ===
print("=" * 100)
print("Per-day stability : V10 (clip=50, tw=2)")
print("=" * 100)
set_hyd(fixed_fv=10000, adaptive_fixed_fv=True,
        fixed_fv_book_blend=0.50, fixed_fv_book_clip=50.0,
        make_edge=97, take_width=2, position_limit=200)
pd_total, pd_hyd = bt_all_days()
print(f"{'Day':>5s}  {'Total':>10s}  {'HYD':>10s}  {'non-HYD':>10s}")
for d in (0, 1, 2):
    print(f"  {d:>3d}  {pd_total[d]:>+10.0f}  {pd_hyd[d]:>+10.0f}  {pd_total[d]-pd_hyd[d]:>+10.0f}")
print(f" Total  {sum(pd_total.values()):>+10.0f}  {sum(pd_hyd.values()):>+10.0f}  {sum(pd_total.values())-sum(pd_hyd.values()):>+10.0f}")
print()

# === V1 (current v4) comparison ===
print("=" * 100)
print("Per-day V1 current v4 (clip=10, tw=0) pour comparaison :")
print("=" * 100)
set_hyd(fixed_fv=10000, adaptive_fixed_fv=True,
        fixed_fv_book_blend=0.50, fixed_fv_book_clip=10.0,
        make_edge=97, take_width=0, position_limit=200)
pd_total, pd_hyd = bt_all_days()
for d in (0, 1, 2):
    print(f"  {d:>3d}  {pd_total[d]:>+10.0f}  {pd_hyd[d]:>+10.0f}  {pd_total[d]-pd_hyd[d]:>+10.0f}")
print(f" Total  {sum(pd_total.values()):>+10.0f}  {sum(pd_hyd.values()):>+10.0f}  {sum(pd_total.values())-sum(pd_hyd.values()):>+10.0f}")
print()

# === 100k segment per-day ===
print("=" * 100)
print("First 100k ts segment (live-equivalent) per day — V10 vs V1")
print("=" * 100)
for label, cfg in [
    ("V10 clip=50 tw=2", dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=50.0, make_edge=97, take_width=2, position_limit=200)),
    ("V1  clip=10 tw=0", dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=10.0, make_edge=97, take_width=0, position_limit=200)),
]:
    print(f"  {label}")
    set_hyd(**cfg)
    for d in (0, 1, 2):
        pnl = simulate(d, max_ts=100_000)
        print(f"    day {d}  total={sum(pnl.values()):>+8.0f}  HYD={pnl.get('HYDROGEL_PACK', 0.0):>+8.0f}")
