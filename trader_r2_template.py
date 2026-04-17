"""
trader_r2_template.py — Skeleton plug-and-play pour R2.

STRUCTURE :
  - Keep v32 logic for R1 products (ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT)
    continue à scorer les 5 rounds
  - Demo templates for the 3 most likely R2 formats :
      A) PAIR cointegration (like P1 COCONUTS/PINA_COLADAS)
      B) BASKET / ETF arb (like P2 R3 GIFT_BASKET or P3 R2 PICNIC_BASKET)
      C) CROSS-VENUE arb (like P2 R2 ORCHIDS)
  - All 3 templates are DISABLED by default — enable only when structure confirmed

USAGE POUR R2 :
  1. `python3 analyze_r2.py ROUND_2/` → lire R2_ANALYSIS_REPORT.md
  2. Identifier la structure (pair/basket/cross-venue)
  3. Activer le template correspondant et remplir les constants
  4. Run `local_backtest_v3.py` sur les CSV R2 pour valider
  5. Submit

TOUT LE CODE v32 ORIGINAL EST PRÉSERVÉ — on AJOUTE, on ne REMPLACE pas.
"""
import json
from typing import Dict, List, Optional, Tuple
from datamodel import Order, OrderDepth, TradingState

# Imports des primitives (à concaténer dans ce fichier si submit car IMC n'accepte pas imports locaux)
# from r2_primitives import HardcodedMeanZ, BasketPricer, swmid, safe_order, ...
# Pour simplicité ici, on importera. Pour submit finalement on flattenera tout.


POSITION_LIMIT_DEFAULT = 60  # R2 typique ; à ajuster par produit


# ============================================================================
# R2 CONFIGS — À REMPLIR APRÈS ANALYSE
# ============================================================================

# Position limits confirmées dans le notice PDF
POSITION_LIMITS = {
    "ASH_COATED_OSMIUM": 80,
    "INTARIAN_PEPPER_ROOT": 80,
    # === R2 products (à remplir avec vraies valeurs du PDF) ===
    # "CROISSANTS": 250,
    # "JAMS": 350,
    # "DJEMBES": 60,
    # "PICNIC_BASKET1": 60,
    # "PICNIC_BASKET2": 100,
}


# -------- Template A : PAIR trading (cointegration) --------
PAIR_CONFIG = {
    "enabled": False,
    "product_a": None,          # e.g. "PINA_COLADAS"
    "product_b": None,          # e.g. "COCONUTS"
    # spread_a_b = mid_a - (intercept + slope * mid_b)
    "intercept": 0.0,           # from OLS on CSV
    "slope": 1.875,             # from OLS on CSV
    "spread_mean": 0.0,         # HARDCODED (from CSV sample mean of spread)
    "z_window": 45,             # rolling std window (Linear Utility used 45)
    "entry_z": 1.5,             # P1 used 1.5 (short window gives small z)
    "exit_z": 0.3,
    "target_size_a": 40,
    "target_size_b": 75,        # = target_size_a * slope rounded
}


# -------- Template B : BASKET / ETF arb --------
BASKET_CONFIG = {
    "enabled": False,
    "basket": None,             # e.g. "PICNIC_BASKET1"
    "components": {},           # e.g. {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1}
    "intercept": 0.0,           # basket offset (often 0)
    "spread_mean": 379.5,       # HARDCODED from offline CSV — Linear Utility approach
    "z_window": 45,
    "entry_z": 7.0,             # Linear Utility's threshold (std window short → big z)
    "exit_z": 2.0,
    "target_basket_pos": 58,    # Linear Utility : target 58/60
    "hedge_components": False,  # P3: some teams skip hedge ("trade basket only")
}


# -------- Template C : CROSS-VENUE arb (ORCHIDS-like) --------
CROSS_VENUE_CONFIG = {
    "enabled": False,
    "product": None,            # e.g. "ORCHIDS"
    "edge_vs_foreign_ask": 2,   # local sell price = foreign_ask - 2 (Linear Utility)
    "min_profit": 1.5,          # net edge after frais minimum
    "tariff_import": 0.0,       # from observations
    "tariff_export": 0.0,
    "shipping_cost": 0.0,
    "storage_fee_per_tick": 0.0,  # if long position : pays per tick
}


# ============================================================================
# PRIMITIVES (inlined for single-file submit)
# ============================================================================

def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _mid(depth: OrderDepth) -> Optional[float]:
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bb is not None and ba is not None:
        return (bb + ba) / 2.0
    return float(bb) if bb is not None else (float(ba) if ba is not None else None)


def _swmid(depth: OrderDepth) -> Optional[float]:
    """Size-weighted mid — Linear Utility formula."""
    if not depth.buy_orders or not depth.sell_orders:
        return _mid(depth)
    bb = max(depth.buy_orders.keys())
    ba = min(depth.sell_orders.keys())
    bv = int(depth.buy_orders[bb])
    av = int(abs(depth.sell_orders[ba]))
    if bv + av == 0:
        return (bb + ba) / 2.0
    return (bb * av + ba * bv) / (bv + av)


def _hardcoded_z(x: float, mean: float, history: list, window: int) -> float:
    """Z-score avec mean hardcodé + std rolling court."""
    history.append(float(x))
    if len(history) > window * 2:
        del history[: len(history) - window]
    win = history[-window:]
    if len(win) < 2:
        return 0.0
    var = sum((v - mean) ** 2 for v in win) / max(1, len(win) - 1)
    std = max(1e-6, var ** 0.5)
    return (x - mean) / std


def _safe_order(product: str, price: int, qty: int, cur_pos: int, limit: int) -> Optional[Order]:
    """CRITIQUE : clamp avant envoi (CarterT27 P3 R2 a perdu pour ça)."""
    if qty == 0:
        return None
    if qty > 0:
        max_q = limit - cur_pos
        if max_q <= 0:
            return None
        return Order(product, price, min(qty, max_q))
    else:
        max_q = limit + cur_pos
        if max_q <= 0:
            return None
        return Order(product, price, -min(abs(qty), max_q))


def _cross_to_target(product: str, target_pos: int, cur_pos: int,
                     depth: OrderDepth, limit: int) -> List[Order]:
    """Prend des market orders pour amener la position au target."""
    delta = target_pos - cur_pos
    if delta == 0:
        return []
    orders = []
    if delta > 0:
        # BUY delta
        remaining = delta
        for ask_price in sorted(depth.sell_orders.keys()):
            avail = -depth.sell_orders[ask_price]
            qty = min(remaining, avail)
            safe = _safe_order(product, ask_price, qty, cur_pos, limit)
            if safe is not None:
                orders.append(safe)
                cur_pos += safe.quantity
                remaining -= safe.quantity
            if remaining <= 0:
                break
    else:
        remaining = -delta
        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            avail = depth.buy_orders[bid_price]
            qty = -min(remaining, avail)
            safe = _safe_order(product, bid_price, qty, cur_pos, limit)
            if safe is not None:
                orders.append(safe)
                cur_pos += safe.quantity
                remaining += safe.quantity  # safe.quantity is negative
            if remaining <= 0:
                break
    return orders


# ============================================================================
# R1 LOGIC (v32 equivalent — placeholder, replace with real v32 content on submit)
# ============================================================================

def trade_r1_product(product: str, state: TradingState, trader_data: dict) -> List[Order]:
    """
    Pour le template, on fait passer-through à v32 si dispo.
    En submit final : concat le full code v32 trade_product() ici.
    """
    # TODO: copy full v32 trade_product logic here
    return []


# ============================================================================
# R2 TEMPLATES — Pair / Basket / Cross-venue
# ============================================================================

def trade_pair(state: TradingState, trader_data: dict, cfg: dict) -> Dict[str, List[Order]]:
    """Template A : pair cointegration via Z-score."""
    if not cfg["enabled"]:
        return {}
    a, b = cfg["product_a"], cfg["product_b"]
    depth_a = state.order_depths.get(a)
    depth_b = state.order_depths.get(b)
    if depth_a is None or depth_b is None:
        return {}
    mid_a = _swmid(depth_a)
    mid_b = _swmid(depth_b)
    if mid_a is None or mid_b is None:
        return {}

    spread = mid_a - (cfg["intercept"] + cfg["slope"] * mid_b)
    pstate = trader_data.setdefault("_pair", {"h": []})
    z = _hardcoded_z(spread, cfg["spread_mean"], pstate["h"], cfg["z_window"])

    pos_a = state.position.get(a, 0)
    pos_b = state.position.get(b, 0)
    lim_a = POSITION_LIMITS.get(a, POSITION_LIMIT_DEFAULT)
    lim_b = POSITION_LIMITS.get(b, POSITION_LIMIT_DEFAULT)

    orders = {a: [], b: []}

    if z > cfg["entry_z"]:
        # spread high → short A, long B
        orders[a] = _cross_to_target(a, -cfg["target_size_a"], pos_a, depth_a, lim_a)
        orders[b] = _cross_to_target(b, +cfg["target_size_b"], pos_b, depth_b, lim_b)
    elif z < -cfg["entry_z"]:
        orders[a] = _cross_to_target(a, +cfg["target_size_a"], pos_a, depth_a, lim_a)
        orders[b] = _cross_to_target(b, -cfg["target_size_b"], pos_b, depth_b, lim_b)
    elif abs(z) < cfg["exit_z"]:
        # close positions
        orders[a] = _cross_to_target(a, 0, pos_a, depth_a, lim_a)
        orders[b] = _cross_to_target(b, 0, pos_b, depth_b, lim_b)
    # else : hold

    return orders


def trade_basket(state: TradingState, trader_data: dict, cfg: dict) -> Dict[str, List[Order]]:
    """Template B : basket / ETF arbitrage (P2 R3 / P3 R2 style)."""
    if not cfg["enabled"]:
        return {}
    basket = cfg["basket"]
    components = cfg["components"]
    basket_depth = state.order_depths.get(basket)
    if basket_depth is None:
        return {}

    # Compute synthetic via swmid
    synthetic = float(cfg["intercept"])
    for c, w in components.items():
        d = state.order_depths.get(c)
        if d is None:
            return {}
        mc = _swmid(d)
        if mc is None:
            return {}
        synthetic += w * mc
    basket_mid = _swmid(basket_depth)
    if basket_mid is None:
        return {}

    spread = basket_mid - synthetic
    pstate = trader_data.setdefault("_basket", {"h": []})
    z = _hardcoded_z(spread, cfg["spread_mean"], pstate["h"], cfg["z_window"])

    pos_basket = state.position.get(basket, 0)
    lim_basket = POSITION_LIMITS.get(basket, POSITION_LIMIT_DEFAULT)

    orders: Dict[str, List[Order]] = {basket: []}

    target_basket = 0
    if z > cfg["entry_z"]:
        # basket trop cher → short basket, long components
        target_basket = -cfg["target_basket_pos"]
    elif z < -cfg["entry_z"]:
        target_basket = +cfg["target_basket_pos"]
    elif abs(z) < cfg["exit_z"]:
        target_basket = 0
    else:
        target_basket = pos_basket  # hold

    orders[basket] = _cross_to_target(basket, target_basket, pos_basket,
                                       basket_depth, lim_basket)

    # Optional : hedge components
    if cfg.get("hedge_components", False) and target_basket != pos_basket:
        for c, w in components.items():
            d = state.order_depths.get(c)
            if d is None:
                continue
            pos_c = state.position.get(c, 0)
            lim_c = POSITION_LIMITS.get(c, POSITION_LIMIT_DEFAULT)
            # hedge inverse : long component = -target_basket * weight
            target_c = int(-target_basket * w)
            # clip to limit
            target_c = max(-lim_c, min(lim_c, target_c))
            orders.setdefault(c, []).extend(_cross_to_target(c, target_c, pos_c, d, lim_c))

    return orders


def trade_cross_venue(state: TradingState, trader_data: dict, cfg: dict) -> Dict[str, List[Order]]:
    """Template C : ORCHIDS-like cross-venue arb (P2 R2 style)."""
    if not cfg["enabled"]:
        return {}
    product = cfg["product"]
    depth = state.order_depths.get(product)
    if depth is None:
        return {}

    # Observations doit contenir foreign exchange info
    obs = state.observations
    if obs is None:
        return {}
    foreign = None
    if hasattr(obs, 'conversionObservations'):
        foreign = obs.conversionObservations.get(product)
    if foreign is None:
        return {}

    foreign_ask = getattr(foreign, "askPrice", None)
    foreign_bid = getattr(foreign, "bidPrice", None)
    import_tariff = getattr(foreign, "importTariff", 0)
    export_tariff = getattr(foreign, "exportTariff", 0)
    transport = getattr(foreign, "transportFees", 0)

    if foreign_ask is None or foreign_bid is None:
        return {}

    # Sell locally at foreign_ask - 2, then import from foreign exchange
    sell_price = int(foreign_ask - cfg["edge_vs_foreign_ask"])
    net_profit = sell_price - foreign_ask - import_tariff - transport
    if net_profit < cfg["min_profit"]:
        return {}

    pos = state.position.get(product, 0)
    limit = POSITION_LIMITS.get(product, POSITION_LIMIT_DEFAULT)

    # Short the local at sell_price, then conversion request will import from south
    # (conversion = +N en observations du tick suivant)
    qty = min(limit + pos, 50)  # sell up to limit
    orders = []
    safe = _safe_order(product, sell_price, -qty, pos, limit)
    if safe is not None:
        orders.append(safe)
    return {product: orders}


# ============================================================================
# TRADER CLASS — orchestrate R1 + R2 templates
# ============================================================================

class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}

        # 1. R1 products (v32 logic)
        for product in ("ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"):
            if product in state.order_depths:
                try:
                    result[product] = trade_r1_product(product, state, trader_data)
                except Exception as e:
                    print(f"ERR R1 {state.timestamp} {product} {e}")
                    result[product] = []

        # 2. R2 templates (only active ones)
        for template_name, template_fn, cfg in [
            ("pair", trade_pair, PAIR_CONFIG),
            ("basket", trade_basket, BASKET_CONFIG),
            ("cross_venue", trade_cross_venue, CROSS_VENUE_CONFIG),
        ]:
            if not cfg.get("enabled", False):
                continue
            try:
                t_orders = template_fn(state, trader_data, cfg)
                for p, os in t_orders.items():
                    result.setdefault(p, []).extend(os)
            except Exception as e:
                print(f"ERR R2/{template_name} {state.timestamp} {e}")

        # 3. Conversions request (for cross-venue arb)
        conversions = 0
        if CROSS_VENUE_CONFIG.get("enabled", False):
            product = CROSS_VENUE_CONFIG["product"]
            pos = state.position.get(product, 0)
            if pos < 0:
                conversions = -pos  # import to cover short

        # 4. Serialize trader_data
        try:
            out = json.dumps(trader_data, separators=(",", ":"))
            if len(out) > 49000:
                # Trim history buffers aggressively
                for k in list(trader_data.keys()):
                    if isinstance(trader_data[k], dict) and "h" in trader_data[k]:
                        trader_data[k]["h"] = trader_data[k]["h"][-50:]
                out = json.dumps(trader_data, separators=(",", ":"))
        except Exception:
            out = ""

        return result, conversions, out

    def bid(self) -> int:
        return 0
