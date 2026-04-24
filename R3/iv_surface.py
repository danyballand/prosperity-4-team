"""
IV surface fit + residual Z-score — standalone module.

Fit quadratique y = a x² + b x + c, avec x = ln(K/S), y = IV_market.
Retourne le résidu IV pour un strike cible + Z-score lissé via EWM.

Inspired by Codex P1 : smile convexe creusé, VEV_5400 présente edge +1.43 ticks
en LONG (IV sous-évaluée vs surface fit). P1 follow-up : résidu AR(1)=0.948,
half-life 12.9 ts → Z-score tradeable.

Usage :
  from iv_surface import fit_iv_surface, residual_for_strike
  surface = fit_iv_surface(iv_points)   # [(ln_moneyness, iv), ...]
  r = residual_for_strike(surface, ln_K_over_S, iv_market)
"""
import math


def fit_quadratic(xs, ys):
    """
    Moindres carrés ordinaires pour y = a x² + b x + c.
    Pas de numpy : matrice normale 3x3 inversée manuellement.
    Retourne (a, b, c) ou None si moins de 3 points.
    """
    n = len(xs)
    if n < 3:
        return None

    # Sommes nécessaires
    sx  = sum(xs)
    sx2 = sum(x * x for x in xs)
    sx3 = sum(x ** 3 for x in xs)
    sx4 = sum(x ** 4 for x in xs)
    sy  = sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sx2y = sum(x * x * y for x, y in zip(xs, ys))

    # Matrice normale :
    # [[sx4, sx3, sx2],   [[a],     [[sx2y],
    #  [sx3, sx2, sx ],  ×  [b],  =   [sxy ],
    #  [sx2, sx , n  ]]    [c]]      [sy  ]]
    M = [
        [sx4, sx3, sx2, sx2y],
        [sx3, sx2, sx,  sxy ],
        [sx2, sx,  n,   sy  ],
    ]

    # Gauss-Jordan élimination avec pivot partiel
    for i in range(3):
        # Pivot
        pivot_idx = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[pivot_idx][i]) < 1e-12:
            return None  # matrice singulière
        M[i], M[pivot_idx] = M[pivot_idx], M[i]
        pivot = M[i][i]
        for j in range(i, 4):
            M[i][j] /= pivot
        for k in range(3):
            if k == i:
                continue
            factor = M[k][i]
            for j in range(i, 4):
                M[k][j] -= factor * M[i][j]

    return M[0][3], M[1][3], M[2][3]  # (a, b, c)


def evaluate_surface(coefs, x):
    """Évalue le polynôme (a,b,c) en x."""
    a, b, c = coefs
    return a * x * x + b * x + c


class IVSurfaceTracker:
    """
    Track le résidu IV d'un strike cible + Z-score via EMA.

    Serializable pour trader_data : dump() / load().
    Budget mémoire : 6 floats (ema_mean, ema_var, count, last_residual, + 2 reserve)
    """
    EMA_ALPHA = 0.02  # half-life ~ 34 ticks, stable stats sur plusieurs trades

    def __init__(self):
        self.count = 0
        self.ema_mean = 0.0
        self.ema_var = 0.0
        self.last_residual = 0.0

    def update(self, residual):
        """Update EMA stats with new residual."""
        self.count += 1
        if self.count == 1:
            self.ema_mean = residual
            self.ema_var = 0.0
        else:
            delta = residual - self.ema_mean
            self.ema_mean += self.EMA_ALPHA * delta
            self.ema_var = (1.0 - self.EMA_ALPHA) * (self.ema_var + self.EMA_ALPHA * delta * delta)
        self.last_residual = residual

    def z_score(self, residual):
        """Retourne Z = (residual - mean) / std. None si pas assez d'obs."""
        if self.count < 30 or self.ema_var <= 0:
            return None
        std = math.sqrt(self.ema_var)
        if std < 1e-8:
            return None
        return (residual - self.ema_mean) / std

    def dump(self):
        return {
            "count": self.count,
            "mean": round(self.ema_mean, 6),
            "var":  round(self.ema_var, 8),
            "last": round(self.last_residual, 6),
        }

    @classmethod
    def load(cls, d):
        obj = cls()
        if d:
            obj.count         = int(d.get("count", 0))
            obj.ema_mean      = float(d.get("mean", 0.0))
            obj.ema_var       = float(d.get("var", 0.0))
            obj.last_residual = float(d.get("last", 0.0))
        return obj


# ========== Self-test ==========
if __name__ == "__main__":
    # Test 1 : fit parfait (y = x²) → a=1, b=0, c=0
    xs = [-2, -1, 0, 1, 2]
    ys = [4, 1, 0, 1, 4]
    a, b, c = fit_quadratic(xs, ys)
    assert abs(a - 1.0) < 1e-9, f"a: {a}"
    assert abs(b - 0.0) < 1e-9, f"b: {b}"
    assert abs(c - 0.0) < 1e-9, f"c: {c}"

    # Test 2 : IV smile simulé (Codex P1 day 0 : a=6.44, b=-0.037, c=0.208)
    strikes = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
    S = 5250.0
    a_true, b_true, c_true = 6.44, -0.037, 0.208
    xs = [math.log(k / S) for k in strikes]
    ys = [a_true * x * x + b_true * x + c_true for x in xs]
    a, b, c = fit_quadratic(xs, ys)
    assert abs(a - a_true) < 0.01, f"smile a: {a} vs {a_true}"
    assert abs(b - b_true) < 0.01, f"smile b: {b}"

    # Test 3 : residual + Z-score tracker
    tracker = IVSurfaceTracker()
    import random
    random.seed(42)
    # Simule 500 résidus normaux autour de 0 avec std=0.005
    for _ in range(500):
        r = random.gauss(0, 0.005)
        tracker.update(r)
    z = tracker.z_score(-0.015)
    assert z is not None and z < -2.0, f"Z-score extreme: {z}"
    z_normal = tracker.z_score(0.0)
    assert z_normal is not None and abs(z_normal) < 1.0, f"Z-score normal: {z_normal}"

    # Test 4 : dump / load round trip
    d = tracker.dump()
    tracker2 = IVSurfaceTracker.load(d)
    assert tracker2.count == tracker.count
    assert abs(tracker2.ema_mean - tracker.ema_mean) < 1e-6

    print("All iv_surface tests passed.")
    print(f"  Simulated smile fit: a={a:.3f} b={b:.4f} c={c:.4f}  (true: {a_true}, {b_true}, {c_true})")
    print(f"  Tracker stats after 500 obs: mean={tracker.ema_mean:+.5f} std={math.sqrt(tracker.ema_var):.5f}")
    print(f"  Z(-0.015) = {z:.2f}  (should be ≈ -3)")
