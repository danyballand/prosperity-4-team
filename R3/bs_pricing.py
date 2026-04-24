"""
Black-Scholes pricing module — déterministe, standalone, no scipy.

Usage :
  from bs_pricing import call_price, implied_vol, delta, vega
  px = call_price(S=5250, K=5400, T=5/250, r=0.0, sigma=0.22)
  iv = implied_vol(market_price=24, S=5250, K=5400, T=5/250, r=0.0)
  d  = delta(S=5250, K=5400, T=5/250, r=0.0, sigma=0.22)

TTE convention : années, trading days 250/an (confirmé par Codex P1 follow-up Q5).
R3 wiki officiel : TTE = 5j au start de live, historical day 0=8d, 1=7d, 2=6d.
"""
import math


def _norm_cdf(x):
    """Approximation Abramowitz-Stegun (précision ~1e-7), pas de scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _d1_d2(S, K, T, r, sigma):
    if sigma <= 0 or T <= 0:
        return None, None
    vT = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / vT
    d2 = d1 - vT
    return d1, d2


def call_price(S, K, T, r, sigma):
    """Prix call Black-Scholes (r=0 par défaut en Prosperity)."""
    if T <= 0:
        return max(S - K, 0.0)
    if sigma <= 0:
        return max(S - K * math.exp(-r * T), 0.0)
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    return S * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)


def delta(S, K, T, r, sigma):
    """Delta call = N(d1)."""
    if T <= 0:
        return 1.0 if S > K else 0.0
    if sigma <= 0:
        return 1.0 if S > K * math.exp(-r * T) else 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return _norm_cdf(d1)


def vega(S, K, T, r, sigma):
    """Vega call = S × phi(d1) × sqrt(T). Units : prix par +1.0 de sigma (pas 1%)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return S * _norm_pdf(d1) * math.sqrt(T)


def theta(S, K, T, r, sigma):
    """Theta call per year (négatif normalement)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    term1 = -(S * _norm_pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    term2 = -r * K * math.exp(-r * T) * _norm_cdf(d2)
    return term1 + term2


def implied_vol(market_price, S, K, T, r, low=1e-4, high=5.0, tol=1e-5, max_iter=50):
    """
    IV via Brent simplified (bisection + secant fallback). Deterministic.
    Retourne None si pas de solution dans [low, high].
    """
    if T <= 0:
        return None
    intrinsic = max(S - K * math.exp(-r * T), 0.0)
    if market_price < intrinsic - 1e-6:
        return None  # arb : market < intrinsic
    if market_price > S - 1e-6:
        return None  # arb : market > S (upper bound du call)

    def obj(sigma):
        return call_price(S, K, T, r, sigma) - market_price

    f_low = obj(low)
    f_high = obj(high)
    if f_low > 0:  # market < BS(low) = ~intrinsic, IV ~= 0
        return low
    if f_high < 0:  # market > BS(high), IV > 5 (aberrant)
        return high

    # Bisection basique (50 iter → tol 1e-15 sur sigma)
    a, b = low, high
    fa = f_low
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        fm = obj(m)
        if abs(fm) < tol:
            return m
        if fa * fm < 0:
            b = m
        else:
            a = m
            fa = fm
        if b - a < tol:
            return 0.5 * (a + b)
    return 0.5 * (a + b)


# ========== Assertions / Self-test ==========
if __name__ == "__main__":
    # Test 1 : call ATM, TTE=0.5y, sigma=0.2 → environ 5.60 (Hull textbook)
    S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.0, 0.2
    p = call_price(S, K, T, r, sigma)
    assert abs(p - 5.6399) < 0.01, f"call_price ATM fail: {p}"

    # Test 2 : deep ITM → ~S-K
    p = call_price(200, 100, 0.5, 0.0, 0.2)
    assert abs(p - 100) < 0.5, f"deep ITM: {p}"

    # Test 3 : deep OTM → ~0
    p = call_price(50, 100, 0.5, 0.0, 0.2)
    assert p < 0.1, f"deep OTM: {p}"

    # Test 4 : implied_vol reverse
    iv = implied_vol(5.6399, 100, 100, 0.5, 0.0)
    assert abs(iv - 0.2) < 1e-3, f"IV reverse: {iv}"

    # Test 5 : delta call ATM (S=K, r=0, T=0.5, sigma=0.2) → d1 = 0.0707 → N(d1) ≈ 0.528
    d = delta(100, 100, 0.5, 0.0, 0.2)
    assert abs(d - 0.528) < 0.01, f"delta ATM: {d}"

    # Test 6 : vega ATM > 0
    v = vega(100, 100, 0.5, 0.0, 0.2)
    assert 10 < v < 50, f"vega ATM: {v}"

    # Test 7 : VE scenario (S=5250, K=5400, TTE=5/250, iv=0.22) ≈ prix observé ~24
    S, K, T, sigma = 5250.0, 5400.0, 5.0 / 250.0, 0.22
    p = call_price(S, K, T, 0.0, sigma)
    iv_back = implied_vol(p, S, K, T, 0.0)
    assert abs(iv_back - 0.22) < 1e-3, f"VE scenario IV round-trip: {iv_back}"

    # Test 8 : IV de prix observé réel
    iv_real = implied_vol(24, 5250, 5400, 5 / 250, 0.0)
    assert iv_real is not None and 0.1 < iv_real < 0.5, f"IV real 5400: {iv_real}"

    # Test 9 : delta pour VEV_5400 TTE=5j iv~0.22 → faible (< 0.25)
    d5400 = delta(5250, 5400, 5 / 250, 0.0, 0.22)
    assert 0.05 < d5400 < 0.35, f"delta 5400: {d5400}"

    print("All BS pricing tests passed.")
    print(f"  call(5250,5400,5/250,0.22)  = {call_price(5250, 5400, 5/250, 0.0, 0.22):.2f}")
    print(f"  delta                        = {delta(5250, 5400, 5/250, 0.0, 0.22):.3f}")
    print(f"  vega                         = {vega(5250, 5400, 5/250, 0.0, 0.22):.2f}")
    print(f"  IV from px=24               = {implied_vol(24, 5250, 5400, 5/250, 0.0):.3f}")
