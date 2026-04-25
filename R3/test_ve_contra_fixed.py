"""
VE contrarian FIX : utilise mid_now (bb+ba)/2 au lieu de wall_mid filtré.
Tests grille seuils + window momentum.
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


def run_jour2(thresh, target, window):
    reset()
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian"] = True
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_thresh"] = thresh
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_target"] = target
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_window"] = window
    pnl = simulate(2, max_ts=100_000)
    return sum(pnl.values()), pnl.get("VELVETFRUIT_EXTRACT", 0), pnl.get("HYDROGEL_PACK", 0)


def run_3d(thresh, target, window):
    reset()
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian"] = True
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_thresh"] = thresh
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_target"] = target
    PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_window"] = window
    total = 0; ve = 0; hyd = 0
    for d in (0, 1, 2):
        pnl = simulate(d)
        total += sum(pnl.values())
        ve += pnl.get("VELVETFRUIT_EXTRACT", 0)
        hyd += pnl.get("HYDROGEL_PACK", 0)
    return total, ve, hyd


print("=" * 100, flush=True)
print("VE CONTRARIAN FIX (mid_now) — grille thresh × target × window", flush=True)
print("=" * 100, flush=True)

# v9 baseline
reset()
pnl = simulate(2, max_ts=100_000)
v9_total = sum(pnl.values())
v9_ve = pnl.get("VELVETFRUIT_EXTRACT", 0)
v9_hyd = pnl.get("HYDROGEL_PACK", 0)
print(f"v9 baseline jour2_100k : TOTAL={v9_total:+.0f}  VE={v9_ve:+.0f}  HYD={v9_hyd:+.0f}", flush=True)
print(flush=True)

print(f"{'config':<35s}  {'TOTAL':>8s}  {'VE':>7s}  {'HYD':>8s}  {'Δ vs v9':>8s}", flush=True)
print("-" * 100, flush=True)

best = None
best_t = v9_total
configs = []
for window in [3, 5, 7, 10, 15]:
    for thresh in [1.0, 1.5, 2.0, 3.0, 5.0]:
        for target in [80, 150, 200]:
            configs.append((thresh, target, window))

for thresh, target, window in configs:
    t, ve, hyd = run_jour2(thresh, target, window)
    delta = t - v9_total
    flag = ""
    if t > best_t + 200:
        best_t = t; best = (thresh, target, window, t, ve, hyd); flag = " ★"
    print(f"th={thresh} tgt={target} w={window:<3d} {'':<10s}  {t:>+8.0f}  {ve:>+7.0f}  {hyd:>+8.0f}  {delta:>+8.0f}{flag}", flush=True)

print(flush=True)
if best:
    thresh, target, window, t, ve, hyd = best
    print(f"BEST : th={thresh} tgt={target} w={window} → jour2_100k = {t:+.0f}  (Δ={t-v9_total:+.0f})", flush=True)
    # 3d régression
    t3, ve3, hyd3 = run_3d(thresh, target, window)
    print(f"  3d régression : TOTAL={t3:+.0f}  VE={ve3:+.0f}  HYD={hyd3:+.0f}", flush=True)
else:
    print("AUCUN gain > 200 vs v9 sur jour 2 100k", flush=True)
