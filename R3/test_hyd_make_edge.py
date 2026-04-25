"""
Fix critique : HYD make_edge=97 quote 9903/10097 alors que le range live est 9915-10031.
Tester make_edge réduit pour quoter DANS la zone d'oscillation et capturer les fills passifs.

Test sur jour 2 0-100k UNIQUEMENT (la fenêtre live R3).
Aussi tester sur 3j×1M pour confirmer pas de régression.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


def run_jour2_100k(make_edge, take_width=None, clip=None):
    reset()
    PP["HYDROGEL_PACK"]["make_edge"] = make_edge
    if take_width is not None:
        PP["HYDROGEL_PACK"]["take_width"] = take_width
    if clip is not None:
        PP["HYDROGEL_PACK"]["fixed_fv_book_clip"] = clip
    pnl = simulate(2, max_ts=100_000)
    total = sum(pnl.values())
    hyd = pnl.get("HYDROGEL_PACK", 0)
    return total, hyd, pnl


def run_3d(make_edge, take_width=None, clip=None):
    reset()
    PP["HYDROGEL_PACK"]["make_edge"] = make_edge
    if take_width is not None:
        PP["HYDROGEL_PACK"]["take_width"] = take_width
    if clip is not None:
        PP["HYDROGEL_PACK"]["fixed_fv_book_clip"] = clip
    total = 0; hyd = 0
    for d in (0, 1, 2):
        pnl = simulate(d)
        total += sum(pnl.values())
        hyd += pnl.get("HYDROGEL_PACK", 0)
    return total, hyd


print("=" * 100, flush=True)
print("HYD MAKE_EDGE FIX — quote dans le range 9915-10031 au lieu de 9903/10097", flush=True)
print("=" * 100, flush=True)
print("Range live jour 2 0-100k : 9915 → 10031 = 116 ticks. v6 fait +2,391. Max théorique +23k.", flush=True)
print(flush=True)

print(f"{'Variant':<28s}  {'jour2_100k':>12s}  {'HYD jour2':>10s}  {'3d_total':>10s}  {'HYD 3d':>10s}", flush=True)
print("-" * 100, flush=True)

# Baseline
t100, h100, _ = run_jour2_100k(97)
t3d, h3d = run_3d(97)
print(f"{'v6 (edge=97)':<28s}  {t100:>+12.0f}  {h100:>+10.0f}  {t3d:>+10.0f}  {h3d:>+10.0f}", flush=True)

# Variants
configs = [
    ("edge=50",         50, None, None),
    ("edge=30",         30, None, None),
    ("edge=20",         20, None, None),
    ("edge=15",         15, None, None),
    ("edge=10",         10, None, None),
    ("edge=5",          5,  None, None),
    ("edge=15 tw=3",    15, 3,    None),
    ("edge=10 tw=3",    10, 3,    None),
    ("edge=20 tw=3",    20, 3,    None),
    ("edge=15 tw=4",    15, 4,    None),
    ("edge=15 clip=30", 15, None, 30),
    ("edge=10 clip=30 tw=3", 10, 3, 30),
]

best_100k = (None, t100)
for label, edge, tw, clip in configs:
    t100, h100, pnl = run_jour2_100k(edge, tw, clip)
    t3d, h3d = run_3d(edge, tw, clip)
    flag = ""
    if t100 > best_100k[1] + 100:
        best_100k = (label, t100)
        flag = " ★"
    print(f"{label:<28s}  {t100:>+12.0f}  {h100:>+10.0f}  {t3d:>+10.0f}  {h3d:>+10.0f}{flag}", flush=True)

print(flush=True)
print("=" * 100, flush=True)
print(f"BEST sur jour 2 0-100k : {best_100k[0]} = {best_100k[1]:+.0f}", flush=True)
print("=" * 100, flush=True)
print("Si jour2_100k > +6k ET 3d_total > +140k → patch validé pour submit", flush=True)
