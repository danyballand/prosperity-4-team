"""
r2_primitives.py — Building blocks pour stratégies R2+.

Contenu :
  1. Spread trader (pair cointegration / Z-score entry-exit)
  2. Basket pricer (synthetic fair value, detect premium)
  3. Multi-leg order placement (atomic-ish, legging-risk aware)
  4. Regime detector (rolling OLS, coeff drift)
  5. Inventory hedge (net-delta tracker across legs)
  6. Z-score EWMA (rolling mean/std sans numpy)

Tout ce fichier est safe à copier tel quel dans trader.py final — il n'utilise
que stdlib Python. Chaque classe garde son state dans trader_data pour persister
entre ticks (ok pour 49k char budget).
"""
from typing import Dict, List, Optional, Tuple
from datamodel import Order, OrderDepth


# ============================================================================
# 1. Z-SCORE EWMA (state-light rolling mean/std)
# ============================================================================

class ZScoreEWMA:
    """
    Rolling mean/std via EWMA. Pas de fenêtre fixe, juste halflife.
    Retourne z = (x - mean) / std à chaque update.

    Usage :
        z_tracker = ZScoreEWMA.from_state(pstate.setdefault('_z', {}), halflife=100)
        z = z_tracker.update(current_spread)
        pstate['_z'] = z_tracker.to_state()

    Petit footprint : 3 floats en state.
    """

    def __init__(self, halflife: float = 100.0, mean: float = 0.0, var: float = 1.0, n: int = 0):
        self.halflife = halflife
        self.mean = mean
        self.var = var
        self.n = n

    @classmethod
    def from_state(cls, s: dict, halflife: float = 100.0):
        return cls(halflife=halflife,
                   mean=float(s.get("m", 0.0)),
                   var=float(s.get("v", 1.0)),
                   n=int(s.get("n", 0)))

    def to_state(self) -> dict:
        return {"m": self.mean, "v": self.var, "n": self.n}

    def update(self, x: float) -> float:
        """Update EWMA mean/var, return z-score."""
        self.n += 1
        if self.n == 1:
            self.mean = x
            self.var = 1.0  # no variance yet
            return 0.0
        alpha = 1.0 - 0.5 ** (1.0 / max(1.0, self.halflife))
        delta = x - self.mean
        self.mean += alpha * delta
        # incremental var update : var' = (1-α) * (var + α*delta²)
        self.var = (1.0 - alpha) * (self.var + alpha * delta * delta)
        std = max(1e-6, self.var ** 0.5)
        return (x - self.mean) / std

    def current_z(self, x: float) -> float:
        std = max(1e-6, self.var ** 0.5)
        return (x - self.mean) / std


# ============================================================================
# 2. SPREAD TRADER (pair cointegration)
# ============================================================================

class SpreadTrader:
    """
    Pair trading via Z-score du spread.

    spread_t = mid_A - (intercept + slope * mid_B)

    Rules :
      - z > +entry_z  → spread trop haut → SELL A + BUY B (size scaled by |z|)
      - z < -entry_z  → spread trop bas  → BUY A + SELL B
      - |z| < exit_z  → flatten

    Usage :
        trader = SpreadTrader(intercept=100.0, slope=1.875, entry_z=2.0, exit_z=0.5)
        target_pos_A, target_pos_B = trader.target(mid_A, mid_B, cur_pos_A, cur_pos_B, limit=60)
    """

    def __init__(self, intercept: float, slope: float,
                 entry_z: float = 2.0, exit_z: float = 0.5,
                 halflife: float = 200.0, max_size: int = 60):
        self.intercept = intercept
        self.slope = slope
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.halflife = halflife
        self.max_size = max_size

    def compute_spread(self, mid_a: float, mid_b: float) -> float:
        return mid_a - (self.intercept + self.slope * mid_b)

    def signal(self, z: float) -> int:
        """Retourne le signe de la position désirée sur A (short sur B sera opposé)."""
        if z > self.entry_z:
            return -1  # spread haut → short A
        if z < -self.entry_z:
            return +1
        if abs(z) < self.exit_z:
            return 0
        # Dans la zone neutre, maintient la position actuelle si signe correct
        return None  # None = hold (don't change)

    def target_sizes(self, z: float, cur_a: int, cur_b: int,
                     limit_a: int, limit_b: int) -> Tuple[int, int]:
        """
        Retourne (target_pos_A, target_pos_B).
        Sur B, la taille est scalée par slope pour matcher le delta du spread.
        """
        sig = self.signal(z)
        if sig is None:
            return cur_a, cur_b
        if sig == 0:
            return 0, 0
        # Intensity proportionnelle à (|z| - entry_z) clippée
        intensity = min(1.0, max(0.0, (abs(z) - self.entry_z) / self.entry_z))
        size_a = int(sig * min(limit_a, self.max_size) * (0.5 + 0.5 * intensity))
        # Sur B, on hedge avec slope ratio
        size_b = int(-sig * min(limit_b, round(self.max_size * self.slope))
                     * (0.5 + 0.5 * intensity))
        return size_a, size_b


# ============================================================================
# 3. BASKET PRICER (synthetic fair value)
# ============================================================================

class BasketPricer:
    """
    Synthetic fair value pour un basket = intercept + Σ weight_i * component_i.

    Détection mispricing :
        premium = basket_mid - synthetic
        signal via Z-score sur premium

    Usage :
        pricer = BasketPricer(
            intercept=0.0,
            components={"CHOCOLATE": 4.0, "STRAWBERRIES": 6.0, "ROSES": 1.0}
        )
        synthetic = pricer.synthetic_price({"CHOCOLATE": 8000, ...})
        premium = basket_mid - synthetic
    """

    def __init__(self, intercept: float, components: Dict[str, float]):
        self.intercept = intercept
        self.components = components

    def synthetic_price(self, mids: Dict[str, float]) -> Optional[float]:
        total = self.intercept
        for product, weight in self.components.items():
            if product not in mids or mids[product] is None:
                return None
            total += weight * mids[product]
        return total

    def premium(self, basket_mid: float, mids: Dict[str, float]) -> Optional[float]:
        syn = self.synthetic_price(mids)
        if syn is None:
            return None
        return basket_mid - syn


# ============================================================================
# 4. MULTI-LEG ORDER PLACEMENT
# ============================================================================

def multi_leg_orders(legs: Dict[str, Tuple[int, OrderDepth, int]],
                     pos_limits: Dict[str, int],
                     cur_positions: Dict[str, int],
                     target_deltas: Dict[str, int]) -> Dict[str, List[Order]]:
    """
    Place des orders pour atteindre les target_deltas sur plusieurs legs.

    legs : {product: (mid_price_est, OrderDepth, priority)}
        priority = ordre d'exécution (0 = first, utile pour legging : fill leg
        le plus risqué en premier)
    target_deltas : {product: +N pour acheter N, -N pour vendre N}

    Stratégie :
      - Pour chaque leg, poste un IOC-like via take (cross le book)
      - Respecte pos_limits
      - Si le book est trop peu profond, réduit la taille (legging risk awareness)
      - Retourne le dict d'orders à envoyer

    Note : en Prosperity, on ne contrôle pas l'atomicity des legs. Le best effort
    est de take agressivement les N legs au même tick. Si ça fail partiellement,
    le régime detector détecte et hedge au tick suivant.
    """
    orders_out: Dict[str, List[Order]] = {p: [] for p in legs}
    for product, delta in target_deltas.items():
        if product not in legs or delta == 0:
            continue
        _, depth, _ = legs[product]
        limit = pos_limits.get(product, 50)
        cur = cur_positions.get(product, 0)

        if delta > 0:
            # BUY delta units via take sell orders
            remaining = min(delta, limit - cur)
            if remaining <= 0:
                continue
            for ask_price in sorted(depth.sell_orders.keys()):
                ask_qty = -depth.sell_orders[ask_price]
                qty = min(remaining, ask_qty)
                if qty > 0:
                    orders_out[product].append(Order(product, ask_price, qty))
                    remaining -= qty
                if remaining <= 0:
                    break
        else:
            # SELL |delta| units via take buy orders
            remaining = min(abs(delta), limit + cur)
            if remaining <= 0:
                continue
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                bid_qty = depth.buy_orders[bid_price]
                qty = min(remaining, bid_qty)
                if qty > 0:
                    orders_out[product].append(Order(product, bid_price, -qty))
                    remaining -= qty
                if remaining <= 0:
                    break
    return orders_out


# ============================================================================
# 5. REGIME DETECTOR
# ============================================================================

class RegimeDetector:
    """
    Détecte un changement de régime sur la relation x → y (slope drift).
    Rolling OLS sur fenêtre glissante, compare au slope initial.

    Usage :
        detector = RegimeDetector.from_state(pstate.setdefault('_rd', {}),
                                             window=200, expected_slope=1.875)
        drift_flag = detector.update(mid_x, mid_y)
        if drift_flag:
            # re-calibrer intercept/slope ou hedge out
        pstate['_rd'] = detector.to_state()
    """

    def __init__(self, window: int = 200, expected_slope: Optional[float] = None,
                 drift_threshold: float = 0.15,
                 xs: Optional[list] = None, ys: Optional[list] = None):
        self.window = window
        self.expected_slope = expected_slope
        self.drift_threshold = drift_threshold
        self.xs = list(xs) if xs else []
        self.ys = list(ys) if ys else []

    @classmethod
    def from_state(cls, s: dict, window: int = 200,
                   expected_slope: Optional[float] = None,
                   drift_threshold: float = 0.15):
        return cls(window=window, expected_slope=expected_slope,
                   drift_threshold=drift_threshold,
                   xs=s.get("xs", []), ys=s.get("ys", []))

    def to_state(self) -> dict:
        return {"xs": self.xs[-self.window:], "ys": self.ys[-self.window:]}

    def _rolling_slope(self) -> Optional[float]:
        n = min(len(self.xs), len(self.ys))
        if n < 20:
            return None
        xs, ys = self.xs[-self.window:], self.ys[-self.window:]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        num = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs)))
        den = sum((xs[i] - mx) ** 2 for i in range(len(xs)))
        if den == 0:
            return None
        return num / den

    def update(self, x: float, y: float) -> bool:
        """Append and return True si drift detected."""
        self.xs.append(x)
        self.ys.append(y)
        if len(self.xs) > self.window * 2:
            self.xs = self.xs[-self.window:]
            self.ys = self.ys[-self.window:]
        cur_slope = self._rolling_slope()
        if cur_slope is None or self.expected_slope is None:
            return False
        drift = abs(cur_slope - self.expected_slope) / max(1e-6, abs(self.expected_slope))
        return drift > self.drift_threshold

    def current_slope(self) -> Optional[float]:
        return self._rolling_slope()


# ============================================================================
# 6. INVENTORY HEDGE (net delta tracker)
# ============================================================================

def net_delta(positions: Dict[str, int], weights: Dict[str, float]) -> float:
    """
    Expose nette d'un portefeuille multi-legs.
    Ex : si basket - 4·chocolate - 6·strawberries - 1·roses, les weights sont
         {basket: +1, chocolate: -4, strawberries: -6, roses: -1}.
    Une net_delta proche de 0 = bien hedgé.
    """
    return sum(positions.get(p, 0) * w for p, w in weights.items())


def suggest_hedge(positions: Dict[str, int], weights: Dict[str, float],
                  hedge_product: str, max_hedge_size: int = 30) -> int:
    """
    Si net_delta trop éloigné de 0, suggère une taille d'hedge sur hedge_product.
    Returns signed integer : +N = acheter N, -N = vendre N.
    """
    delta = net_delta(positions, weights)
    if abs(delta) < 1e-3:
        return 0
    # Hedge via le produit de poids unitaire (souvent le basket lui-même)
    hedge_weight = weights.get(hedge_product, 1.0)
    if abs(hedge_weight) < 1e-6:
        return 0
    target = -delta / hedge_weight
    return int(max(-max_hedge_size, min(max_hedge_size, round(target))))


# ============================================================================
# 7. UTILITIES
# ============================================================================

# ============================================================================
# 8. LINEAR UTILITY TRICKS (Prosperity 2 rank 2 — used in P2 R3 basket)
# ============================================================================

def swmid(depth: OrderDepth) -> Optional[float]:
    """
    Size-weighted mid (Linear Utility formula used for basket spread).
    swmid = (best_bid * best_ask_vol + best_ask * best_bid_vol) / (bid_vol + ask_vol)

    NOTE : c'est l'inverse du microprice classique. Linear Utility l'utilise
    comme proxy du vrai mid sur le basket et ses composants. C'est le prix
    auquel un taker équilibré paierait.
    """
    if not depth.buy_orders or not depth.sell_orders:
        return None
    bb = max(depth.buy_orders.keys())
    ba = min(depth.sell_orders.keys())
    bv = int(depth.buy_orders[bb])
    av = int(abs(depth.sell_orders[ba]))
    if bv + av == 0:
        return (bb + ba) / 2.0
    return (bb * av + ba * bv) / (bv + av)


class HardcodedMeanZ:
    """
    Z-score avec **mean hardcodé** (offline sample) + **std rolling court**.
    C'est EXACTEMENT l'approche Linear Utility P2 R3 basket :
        default_spread_mean = 379.50 (hardcoded from offline data)
        spread_std_window   = 45 ticks
        zscore_threshold    = 7 (!) — parce que std court est bruyant

    Leçon critique : un rolling_mean lent converge vers le prix courant quand
    le spread persiste → z_score reste petit → zéro trade. Un mean hardcodé
    capture la vraie oscillation.

    Usage :
        z_tracker = HardcodedMeanZ(mean=379.50, window=45)
        z_tracker.load(pstate.setdefault('_hz', {}))
        z = z_tracker.update(current_spread)
        pstate['_hz'] = z_tracker.save()

    State persisté : seulement une fenêtre de 45 floats (~450 chars).
    """

    def __init__(self, mean: float, window: int = 45, history: Optional[list] = None):
        self.mean = float(mean)
        self.window = int(window)
        self.history = list(history) if history else []

    def load(self, s: dict):
        self.history = list(s.get("h", []))
        return self

    def save(self) -> dict:
        return {"h": self.history[-self.window:]}

    def update(self, x: float) -> float:
        self.history.append(float(x))
        if len(self.history) > self.window * 2:
            self.history = self.history[-self.window:]
        window_vals = self.history[-self.window:]
        n = len(window_vals)
        if n < 2:
            return 0.0
        # std par rapport au MEAN HARDCODÉ (pas moyenne rolling !)
        var = sum((v - self.mean) ** 2 for v in window_vals) / max(1, n - 1)
        std = max(1e-6, var ** 0.5)
        return (x - self.mean) / std


# ============================================================================
# 9. POSITION LIMIT GUARD (leçon CarterT27 P3 R2)
# ============================================================================

def safe_order(product: str, price: int, qty: int, cur_pos: int,
               limit: int) -> Optional[Order]:
    """
    CRITIQUE : tout ordre qui ferait dépasser la limite est REJETÉ par le match
    engine (pas clamp). CarterT27 (rank 9 global P3) a perdu R2 à cause de ça.
    Toujours clamp avant d'envoyer.

    qty > 0 → BUY, qty < 0 → SELL
    """
    if qty == 0:
        return None
    if qty > 0:
        max_buy = limit - cur_pos
        if max_buy <= 0:
            return None
        return Order(product, price, min(qty, max_buy))
    else:
        max_sell = limit + cur_pos
        if max_sell <= 0:
            return None
        return Order(product, price, -min(abs(qty), max_sell))


# ============================================================================
# 10. UTILITIES
# ============================================================================

def best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def mid_price(depth: OrderDepth) -> Optional[float]:
    bb = best_bid(depth)
    ba = best_ask(depth)
    if bb is not None and ba is not None:
        return (bb + ba) / 2.0
    return float(bb) if bb is not None else (float(ba) if ba is not None else None)


def clamp_order_qty(desired: int, cur_pos: int, side: str, limit: int) -> int:
    """Clamp desired qty so final position respects limit. side = 'BUY' or 'SELL'."""
    if desired <= 0:
        return 0
    if side.upper() == "BUY":
        return max(0, min(desired, limit - cur_pos))
    else:
        return max(0, min(desired, limit + cur_pos))


# ============================================================================
# SELF-TEST
# ============================================================================

if __name__ == "__main__":
    # Quick sanity on all primitives
    print("=== r2_primitives self-test ===\n")

    # ZScoreEWMA
    z = ZScoreEWMA(halflife=50)
    vals = [0, 0.1, 0.2, 0.1, 0, -0.1, 0, 3.0, 0, 0]  # spike at index 7
    print("ZScoreEWMA test (spike detection):")
    for v in vals:
        zz = z.update(v)
        print(f"  x={v:+5.2f}  z={zz:+6.2f}  mean={z.mean:+.3f}  std={z.var**0.5:.3f}")

    # SpreadTrader
    print("\nSpreadTrader test (A = 100 + 1.5*B):")
    st = SpreadTrader(intercept=100.0, slope=1.5, entry_z=2.0, exit_z=0.5)
    # Suppose mid_A should be 100 + 1.5*500 = 850. If mid_A = 870, spread = +20.
    spread = st.compute_spread(870, 500)
    print(f"  mid_A=870 mid_B=500  spread={spread:+.2f}  (expect +20)")
    # With z=3.0 (beyond entry)
    ta, tb = st.target_sizes(z=3.0, cur_a=0, cur_b=0, limit_a=60, limit_b=100)
    print(f"  z=+3.0 → target_A={ta}  target_B={tb}  (expect negative A, positive B)")

    # BasketPricer
    print("\nBasketPricer test (basket = 4*choco + 6*straw + 1*rose):")
    bp = BasketPricer(intercept=0.0,
                      components={"CHOCOLATE": 4.0, "STRAWBERRIES": 6.0, "ROSES": 1.0})
    syn = bp.synthetic_price({"CHOCOLATE": 8000, "STRAWBERRIES": 4000, "ROSES": 15000})
    print(f"  synthetic = {syn}  (expect 4*8000+6*4000+1*15000 = 71000)")
    prem = bp.premium(72000, {"CHOCOLATE": 8000, "STRAWBERRIES": 4000, "ROSES": 15000})
    print(f"  premium (basket=72000) = {prem}  (expect +1000)")

    # Hedge
    print("\nHedge suggestion test:")
    pos = {"BASKET": 10, "CHOCOLATE": -30, "STRAWBERRIES": -50, "ROSES": -5}
    w = {"BASKET": 1.0, "CHOCOLATE": -4.0, "STRAWBERRIES": -6.0, "ROSES": -1.0}
    d = net_delta(pos, w)
    print(f"  net_delta = {d}  (expect 10 + 120 + 300 + 5 = +435)")
    hedge = suggest_hedge(pos, w, "BASKET", max_hedge_size=50)
    print(f"  hedge on BASKET = {hedge}  (expect -50 clipped from -435)")

    # HardcodedMeanZ
    print("\nHardcodedMeanZ (Linear Utility approach):")
    hz = HardcodedMeanZ(mean=379.5, window=45)
    # simulate spread oscillating around 379.5
    import math
    for i, s in enumerate([379.5, 380, 385, 400, 450, 455, 380, 370, 379, 379]):
        z = hz.update(s)
        print(f"  spread={s:>6.1f}  z={z:+6.2f}")
    print(f"  state size (chars of json) ~ {len(str(hz.save()))}")

    print("\n=== All primitives functional ===")
