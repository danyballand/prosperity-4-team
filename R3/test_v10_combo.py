"""
v10 = v9 (HYD regime) + VE contrarian + VEV ITM edge réduit (penny inside).

Test sur jour 2 0-100k (live) + 3j × 1M.
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


def run_jour2(ve_contrarian=False, ve_thresh=5.0, ve_target=100,
              vev_edge_4500=None, vev_edge_5000=None,
              hyd_regime=True):
    reset()
    PP["HYDROGEL_PACK"]["hyd_regime"] = hyd_regime
    if ve_contrarian:
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian"] = True
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_thresh"] = ve_thresh
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_target"] = ve_target
    if vev_edge_4500 is not None:
        PP["VEV_4000"]["make_edge"] = vev_edge_4500
        PP["VEV_4500"]["make_edge"] = vev_edge_4500
    if vev_edge_5000 is not None:
        PP["VEV_5000"]["make_edge"] = vev_edge_5000
        PP["VEV_5100"]["make_edge"] = vev_edge_5000
    pnl = simulate(2, max_ts=100_000)
    total = sum(pnl.values())
    return total, pnl


def run_3d(ve_contrarian=False, ve_thresh=5.0, ve_target=100,
           vev_edge_4500=None, vev_edge_5000=None, hyd_regime=True):
    reset()
    PP["HYDROGEL_PACK"]["hyd_regime"] = hyd_regime
    if ve_contrarian:
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian"] = True
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_thresh"] = ve_thresh
        PP["VELVETFRUIT_EXTRACT"]["ve_contrarian_target"] = ve_target
    if vev_edge_4500 is not None:
        PP["VEV_4000"]["make_edge"] = vev_edge_4500
        PP["VEV_4500"]["make_edge"] = vev_edge_4500
    if vev_edge_5000 is not None:
        PP["VEV_5000"]["make_edge"] = vev_edge_5000
        PP["VEV_5100"]["make_edge"] = vev_edge_5000
    total = 0; by = {}
    for d in (0, 1, 2):
        pnl = simulate(d)
        total += sum(pnl.values())
        for k, v in pnl.items(): by[k] = by.get(k, 0) + v
    return total, by


print("=" * 110, flush=True)
print("v10 COMBO — HYD regime (déjà actif) + VE contrarian + VEV ITM edge réduit", flush=True)
print("=" * 110, flush=True)

# Headers
def fmt(t, p):
    hyd = p.get("HYDROGEL_PACK", 0)
    ve = p.get("VELVETFRUIT_EXTRACT", 0)
    vev = sum(p.get(f"VEV_{s}", 0) for s in [4000, 4500, 5000, 5100])
    return f"TOTAL={t:>+8.0f}  HYD={hyd:>+7.0f}  VE={ve:>+6.0f}  VEV_ITM={vev:>+6.0f}"


print("\n--- JOUR 2 0-100k (= live R3) ---", flush=True)
print(f"{'Variant':<45s}  result", flush=True)
print("-" * 110, flush=True)

# Baseline = v9 (HYD regime only)
t, p = run_jour2()
print(f"{'v9 baseline (HYD regime only)':<45s}  {fmt(t,p)}", flush=True)
v9_t = t

# VE contrarian sweep
configs_ve = [
    ("v9 + VE contra th=3 tgt=100",    {"ve_contrarian": True, "ve_thresh": 3.0, "ve_target": 100}),
    ("v9 + VE contra th=5 tgt=100",    {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 100}),
    ("v9 + VE contra th=5 tgt=150",    {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 150}),
    ("v9 + VE contra th=5 tgt=200",    {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 200}),
    ("v9 + VE contra th=10 tgt=200",   {"ve_contrarian": True, "ve_thresh": 10.0, "ve_target": 200}),
]
for label, kwargs in configs_ve:
    t, p = run_jour2(**kwargs)
    delta = t - v9_t
    print(f"{label:<45s}  {fmt(t,p)}  Δ={delta:+.0f}", flush=True)

# VEV ITM edge réduit
configs_vev = [
    ("v9 + VEV4000/4500 edge=3",                  {"vev_edge_4500": 3}),
    ("v9 + VEV4000/4500 edge=2",                  {"vev_edge_4500": 2}),
    ("v9 + VEV4000/4500 edge=1",                  {"vev_edge_4500": 1}),
    ("v9 + VEV5000/5100 edge=1",                  {"vev_edge_5000": 1}),
    ("v9 + ALL VEV ITM edge=1",                   {"vev_edge_4500": 1, "vev_edge_5000": 1}),
    ("v9 + ALL VEV ITM edge=2",                   {"vev_edge_4500": 2, "vev_edge_5000": 2}),
]
for label, kwargs in configs_vev:
    t, p = run_jour2(**kwargs)
    delta = t - v9_t
    print(f"{label:<45s}  {fmt(t,p)}  Δ={delta:+.0f}", flush=True)

# Combo total
print(flush=True)
print("--- COMBO COMPLETS ---", flush=True)
combos = [
    ("v10a: HYD + VE_th5_t150 + VEV_ITM_e1",
     {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 150,
      "vev_edge_4500": 1, "vev_edge_5000": 1}),
    ("v10b: HYD + VE_th5_t200 + VEV_ITM_e1",
     {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 200,
      "vev_edge_4500": 1, "vev_edge_5000": 1}),
    ("v10c: HYD + VE_th3_t100 + VEV_ITM_e2",
     {"ve_contrarian": True, "ve_thresh": 3.0, "ve_target": 100,
      "vev_edge_4500": 2, "vev_edge_5000": 2}),
    ("v10d: HYD + VE_th5_t150 + VEV_ITM_e2",
     {"ve_contrarian": True, "ve_thresh": 5.0, "ve_target": 150,
      "vev_edge_4500": 2, "vev_edge_5000": 2}),
]
best_combo = None
best_t = v9_t
for label, kwargs in combos:
    t, p = run_jour2(**kwargs)
    delta = t - v9_t
    print(f"{label:<45s}  {fmt(t,p)}  Δ={delta:+.0f}", flush=True)
    if t > best_t:
        best_t = t; best_combo = (label, kwargs, t, p)

# 3j régression
print(flush=True)
print("--- BEST COMBO 3j × 1M régression ---", flush=True)
if best_combo:
    label, kwargs, _, _ = best_combo
    t3, by3 = run_3d(**kwargs)
    print(f"{label:<45s}  3d_TOTAL={t3:+.0f}", flush=True)
    print(f"  HYD 3d   = {by3.get('HYDROGEL_PACK',0):+.0f}", flush=True)
    print(f"  VE 3d    = {by3.get('VELVETFRUIT_EXTRACT',0):+.0f}", flush=True)
    print(f"  VEV ITM 3d = {sum(by3.get(f'VEV_{s}',0) for s in [4000,4500,5000,5100]):+.0f}", flush=True)

# v9 baseline 3j pour comparaison
t3_v9, by3_v9 = run_3d()
print(f"{'v9 baseline 3d':<45s}  3d_TOTAL={t3_v9:+.0f}", flush=True)

print(flush=True)
print("=" * 110, flush=True)
print("DÉCISION :", flush=True)
print("  Si best combo > v9 (+16k jour2_100k) ET 3d > +120k → submit v10", flush=True)
print("=" * 110, flush=True)
