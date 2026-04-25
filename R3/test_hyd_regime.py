"""
Test HYD régime-based.
Logique :
  mid >= 10010                → SHORT aggressive
  mid < 9950 + mom_5 > 0      → LONG_CAP aggressive
  mid < 9950 + mom_5 ≤ 0      → WAIT (pas de take, MM léger long)
  9970-10010 + mom_5 < 0      → AVOID (flatten)
  9970-10010 + mom_5 ≥ 0      → NEUTRAL_MM (passif autour mid)

Test sur jour 2 0-100k (live R3) ET 3j × 1M.
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


def run(use_regime, size_unit=50, jour2_only=False):
    reset()
    if use_regime:
        PP["HYDROGEL_PACK"]["hyd_regime"] = True
        PP["HYDROGEL_PACK"]["hyd_regime_size"] = size_unit
    if jour2_only:
        pnl = simulate(2, max_ts=100_000)
        return sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0), pnl
    total = 0; hyd = 0; by = {}
    for d in (0, 1, 2):
        pnl = simulate(d)
        total += sum(pnl.values())
        hyd += pnl.get("HYDROGEL_PACK", 0)
        for k, v in pnl.items(): by[k] = by.get(k, 0) + v
    return total, hyd, by


print("=" * 100, flush=True)
print("HYD REGIME-BASED — patch alpha asymétrique (autopsie 369858)", flush=True)
print("=" * 100, flush=True)

# ----- JOUR 2 0-100k (= live R3) -----
print(f"\n--- JOUR 2 0-100k (= fenêtre live R3) ---", flush=True)
print(f"{'Variant':<22s}  {'TOTAL':>10s}  {'HYD':>10s}  {'autres':>10s}", flush=True)
print("-" * 60, flush=True)

t0, h0, p0 = run(False, jour2_only=True)
others0 = t0 - h0
print(f"{'v6 baseline':<22s}  {t0:>+10.0f}  {h0:>+10.0f}  {others0:>+10.0f}", flush=True)

for size in [30, 50, 80, 100, 150]:
    t, h, p = run(True, size_unit=size, jour2_only=True)
    others = t - h
    print(f"{'regime size='+str(size):<22s}  {t:>+10.0f}  {h:>+10.0f}  {others:>+10.0f}", flush=True)

# ----- 3j × 1M (régression check) -----
print(f"\n--- 3 jours × 1M (régression check) ---", flush=True)
print(f"{'Variant':<22s}  {'TOTAL':>10s}  {'HYD':>10s}  {'autres':>10s}", flush=True)
print("-" * 60, flush=True)

t0, h0, by0 = run(False)
others0 = t0 - h0
print(f"{'v6 baseline':<22s}  {t0:>+10.0f}  {h0:>+10.0f}  {others0:>+10.0f}", flush=True)

for size in [30, 50, 80, 100, 150]:
    t, h, by = run(True, size_unit=size)
    others = t - h
    print(f"{'regime size='+str(size):<22s}  {t:>+10.0f}  {h:>+10.0f}  {others:>+10.0f}", flush=True)

print()
print("=" * 100, flush=True)
print("DÉCISION :", flush=True)
print("  jour2_100k > +5k vs v6 +3.4k (gain 1.5k+) ET 3d_total > +120k → submit", flush=True)
print("  jour2_100k < v6 → patch foiré, rester v6", flush=True)
