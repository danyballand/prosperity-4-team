"""
IV-aware quoter pour VEV options.

Principe :
  FV théorique = Black-Scholes(S, K, T, r=0, sigma=smile(ln(K/S)))
  où sigma_smile est un fit quadratique sur les autres 9 strikes (leave-one-out).

Si le marché mid d'un VEV s'écarte de ce FV → notre quote (FV ± edge) est naturellement
biaisé vers le retour à la smile. Capte l'alpha de l'énoncé R3 officiel Rook-E1.

Utilisation : _smile_fair_value(state, strike) dans trader_r3.py
"""
import math
from typing import Dict, Optional

try:
    from bs_pricing import call_price, implied_vol
    from iv_surface import fit_quadratic, evaluate_surface
    _OK = True
except ImportError:
    _OK = False

STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
TRADING_DAYS_YEAR = 250


def _mid(depth):
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    return 0.5 * (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys()))


def _tte_days(timestamp):
    """Day 0=8d, day 1=7d, day 2=6d (historical), live=5d."""
    try:
        day_idx = int(timestamp) // 1_000_000
        if 0 <= day_idx <= 2:
            return 8.0 - day_idx
    except Exception:
        pass
    return 5.0


def compute_smile_fv(state, target_strike, min_points=4):
    """
    Retourne le FV théorique BS(S, K, T, sigma_smile) pour target_strike.
    sigma_smile = fit quadratique IV vs ln(K/S) sur tous les strikes SAUF target.
    Retourne None si infra indispo ou pas assez de points.
    """
    if not _OK:
        return None
    depths = state.order_depths
    ve_depth = depths.get("VELVETFRUIT_EXTRACT")
    S = _mid(ve_depth)
    if S is None or S <= 0:
        return None

    tte = _tte_days(state.timestamp) / TRADING_DAYS_YEAR
    if tte <= 0:
        return None

    # Collecte IVs de tous strikes sauf target
    xs, ys = [], []
    for strike in STRIKES:
        if strike == target_strike:
            continue
        d = depths.get(f"VEV_{strike}")
        mid = _mid(d)
        if mid is None or mid <= 0:
            continue
        iv = implied_vol(mid, S, strike, tte, 0.0)
        if iv is None or iv <= 0.01 or iv >= 4.0:
            continue
        xs.append(math.log(strike / S))
        ys.append(iv)

    if len(xs) < min_points:
        return None

    coefs = fit_quadratic(xs, ys)
    if coefs is None:
        return None

    x_target = math.log(target_strike / S)
    sigma_smile = evaluate_surface(coefs, x_target)
    if sigma_smile <= 0.01 or sigma_smile >= 4.0:
        return None

    fv = call_price(S, target_strike, tte, 0.0, sigma_smile)
    # Plancher intrinsic
    fv = max(fv, max(0.0, S - target_strike))
    return float(fv)


if __name__ == "__main__":
    # Self-test rapide
    class MockDepth:
        def __init__(self, b, a):
            self.buy_orders = {b: 10}
            self.sell_orders = {a: -10}

    class MockState:
        def __init__(self):
            self.timestamp = 0
            self.order_depths = {
                "VELVETFRUIT_EXTRACT": MockDepth(5249, 5251),
                "VEV_4000": MockDepth(1250, 1252),
                "VEV_4500": MockDepth(752, 754),
                "VEV_5000": MockDepth(254, 256),
                "VEV_5100": MockDepth(165, 167),
                "VEV_5200": MockDepth(94, 96),
                "VEV_5300": MockDepth(45, 47),
                "VEV_5400": MockDepth(14, 16),
                "VEV_5500": MockDepth(5, 7),
                "VEV_6000": MockDepth(0, 1),
                "VEV_6500": MockDepth(0, 1),
            }

    state = MockState()
    for strike in STRIKES:
        fv = compute_smile_fv(state, strike)
        d = state.order_depths[f"VEV_{strike}"]
        market_mid = _mid(d)
        if fv is not None:
            print(f"  VEV_{strike}: market_mid={market_mid:.2f}  smile_FV={fv:.2f}  "
                  f"Δ={market_mid - fv:+.2f}")
        else:
            print(f"  VEV_{strike}: FV=None")
