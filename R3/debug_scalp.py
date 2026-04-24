"""
Debug du scalping VEV_5400 — instrumente les décisions pour voir :
  - Fréquence des triggers Z < -2 (entry) et Z > 0 (exit)
  - Distribution des résidus et Z-scores
  - Taille position effective dans le temps
  - PnL unrealized vs realized
"""
import os
import sys
import math
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from datamodel import OrderDepth, TradingState, Listing
from local_backtest_r3 import load_prices, load_trades, PRODUCTS, _limit_for, fill_crossing, apply_passive_fills
from bs_pricing import implied_vol
from iv_surface import fit_quadratic, evaluate_surface, IVSurfaceTracker
import trader_r3 as tm

tracker = IVSurfaceTracker()

stats = {
    "n_ticks": 0,
    "n_ivs_valid": 0,
    "n_fits_ok": 0,
    "n_z_entry": 0,     # Z < -2
    "n_z_exit": 0,      # Z > 0
    "n_z_kill": 0,      # Z > 2.5
    "z_history": [],
    "residual_history": [],
    "iv_target_history": [],
    "iv_surface_history": [],
}


def analyze_day(day):
    snapshots = load_prices(day)
    timestamps = sorted(snapshots.keys())
    for ts in timestamps:
        stats["n_ticks"] += 1
        depths = snapshots[ts]
        ve = depths.get("VELVETFRUIT_EXTRACT")
        target = depths.get("VEV_5400")
        if ve is None or target is None:
            continue
        bb_ve, ba_ve = (max(ve.buy_orders) if ve.buy_orders else None,
                        min(ve.sell_orders) if ve.sell_orders else None)
        if bb_ve is None or ba_ve is None:
            continue
        S = 0.5 * (bb_ve + ba_ve)

        day_idx = ts // 1_000_000
        tte_days = 8.0 - day_idx if 0 <= day_idx <= 2 else 5.0
        tte = tte_days / 250.0

        ivs = []
        target_iv = None
        for strike in [4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000]:
            d = depths.get(f"VEV_{strike}")
            if d is None or not d.buy_orders or not d.sell_orders:
                continue
            mid = 0.5 * (max(d.buy_orders) + min(d.sell_orders))
            iv = implied_vol(mid, S, strike, tte, 0.0)
            if iv is None or iv <= 0.01 or iv >= 4.0:
                continue
            ivs.append((math.log(strike / S), iv))
            if strike == 5400:
                target_iv = iv
        if len(ivs) < 5 or target_iv is None:
            continue
        stats["n_ivs_valid"] += 1
        xs = [p[0] for p in ivs]
        ys = [p[1] for p in ivs]
        coefs = fit_quadratic(xs, ys)
        if coefs is None:
            continue
        stats["n_fits_ok"] += 1

        x_target = math.log(5400 / S)
        iv_surface_val = evaluate_surface(coefs, x_target)
        residual = target_iv - iv_surface_val
        stats["residual_history"].append(residual)
        stats["iv_target_history"].append(target_iv)
        stats["iv_surface_history"].append(iv_surface_val)

        tracker.update(residual)
        z = tracker.z_score(residual)
        if z is not None:
            stats["z_history"].append(z)
            if z < -2:
                stats["n_z_entry"] += 1
            elif z > 2.5:
                stats["n_z_kill"] += 1
            elif z > 0:
                stats["n_z_exit"] += 1


for day in (0, 1, 2):
    print(f"Processing day {day}...")
    analyze_day(day)

print()
print("=" * 60)
print(f"Ticks processed       : {stats['n_ticks']}")
print(f"IVs valid (ve+target) : {stats['n_ivs_valid']}")
print(f"Surface fits OK       : {stats['n_fits_ok']}")
print(f"Z < -2 (entry fires)  : {stats['n_z_entry']}")
print(f"Z > 0  (exit fires)   : {stats['n_z_exit']}")
print(f"Z > +2.5 (kill fires) : {stats['n_z_kill']}")
print()

if stats["residual_history"]:
    rs = stats["residual_history"]
    rs_mean = sum(rs) / len(rs)
    rs_var = sum((r - rs_mean) ** 2 for r in rs) / len(rs)
    rs_std = math.sqrt(rs_var)
    rs_min = min(rs)
    rs_max = max(rs)
    print(f"Residuals IV         : mean={rs_mean:+.5f} std={rs_std:.5f}  min={rs_min:+.4f} max={rs_max:+.4f}")
    ivt = stats["iv_target_history"]
    print(f"IV_5400 market       : mean={sum(ivt)/len(ivt):.4f}  min={min(ivt):.4f} max={max(ivt):.4f}")
    ivs_ = stats["iv_surface_history"]
    print(f"IV_5400 surface fit  : mean={sum(ivs_)/len(ivs_):.4f}")

if stats["z_history"]:
    zs = stats["z_history"]
    n = len(zs)
    zs_sorted = sorted(zs)
    print(f"Z-score distribution (n={n}):")
    print(f"  1%  : {zs_sorted[int(0.01*n)]:+.2f}")
    print(f"  5%  : {zs_sorted[int(0.05*n)]:+.2f}")
    print(f"  50% : {zs_sorted[int(0.5*n)]:+.2f}")
    print(f"  95% : {zs_sorted[int(0.95*n)]:+.2f}")
    print(f"  99% : {zs_sorted[int(0.99*n)]:+.2f}")
