"""
Diagnostic offline : pour chaque strike VEV, calculer les résidus IV vs smile
(leave-one-out fit) sur 3 jours de data historique. Identifier les strikes
avec le plus de résidus exploitables (|Z| > 2).

Pas de backtest, juste analyse des données.
"""
import os, sys, math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bs_pricing import implied_vol
from iv_surface import fit_quadratic, evaluate_surface
from local_backtest_r3 import load_prices

STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
TTE_DAYS = {0: 8, 1: 7, 2: 6}  # wiki R3

def mid_from_depth(depth):
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    return 0.5 * (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys()))


# Per-strike residual stats
stats = {s: {"residuals": [], "ivs": [], "ticks": 0, "mids": []} for s in STRIKES}

for day in (0, 1, 2):
    snapshots = load_prices(day)
    tte_years = TTE_DAYS[day] / 250.0

    for ts in sorted(snapshots.keys()):
        depths = snapshots.get(ts, {})
        ve_depth = depths.get("VELVETFRUIT_EXTRACT")
        S = mid_from_depth(ve_depth)
        if S is None or S <= 0:
            continue

        # Compute IV for each strike
        iv_by_strike = {}
        for strike in STRIKES:
            sym = f"VEV_{strike}"
            d = depths.get(sym)
            mid = mid_from_depth(d)
            if mid is None or mid <= 0:
                continue
            iv = implied_vol(mid, S, strike, tte_years, 0.0)
            if iv is None or iv <= 0.01 or iv >= 4.0:
                continue
            iv_by_strike[strike] = (iv, mid)

        if len(iv_by_strike) < 4:
            continue

        # For each strike : leave-one-out fit, compute residual
        for target_strike in iv_by_strike.keys():
            xs, ys = [], []
            for strike, (iv, _) in iv_by_strike.items():
                if strike == target_strike:
                    continue
                xs.append(math.log(strike / S))
                ys.append(iv)
            coefs = fit_quadratic(xs, ys)
            if coefs is None:
                continue
            x_target = math.log(target_strike / S)
            iv_surface = evaluate_surface(coefs, x_target)
            residual = iv_by_strike[target_strike][0] - iv_surface
            stats[target_strike]["residuals"].append(residual)
            stats[target_strike]["ivs"].append(iv_by_strike[target_strike][0])
            stats[target_strike]["mids"].append(iv_by_strike[target_strike][1])
            stats[target_strike]["ticks"] += 1


print("=" * 90)
print("Diagnostic IV smile résiduels (leave-one-out) — 3 jours historique")
print("=" * 90)
print(f"{'Strike':>7s}  {'N':>6s}  {'IV_mean':>8s}  {'Mid_mean':>9s}  "
      f"{'Res_mean':>9s}  {'Res_std':>8s}  {'|Z|>2 %':>8s}  {'|Z|>3 %':>8s}")
print("-" * 90)

for strike in STRIKES:
    d = stats[strike]
    n = d["ticks"]
    if n == 0:
        print(f"{strike:>7d}  {n:>6d}  {'--':>8s}  {'--':>9s}  {'--':>9s}  {'--':>8s}  {'--':>8s}  {'--':>8s}")
        continue
    res = d["residuals"]
    iv_mean = sum(d["ivs"]) / n
    mid_mean = sum(d["mids"]) / n
    res_mean = sum(res) / n
    res_var = sum((r - res_mean) ** 2 for r in res) / n
    res_std = math.sqrt(res_var)
    # Z-score count
    if res_std > 1e-8:
        z2 = sum(1 for r in res if abs((r - res_mean) / res_std) > 2) / n * 100
        z3 = sum(1 for r in res if abs((r - res_mean) / res_std) > 3) / n * 100
    else:
        z2, z3 = 0, 0
    print(f"{strike:>7d}  {n:>6d}  {iv_mean:>8.4f}  {mid_mean:>9.2f}  "
          f"{res_mean:>+9.4f}  {res_std:>8.4f}  {z2:>7.1f}%  {z3:>7.1f}%")

print()
print("Interprétation :")
print("  Res_mean ≠ 0 → biais systématique (IV constamment au-dessus/dessous surface)")
print("  Res_std grand + |Z|>2 % élevé → outliers fréquents → tradable")
print("  Res_std petit + biais → arb statique : on LONG/SHORT tout le temps")
