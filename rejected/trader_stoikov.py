"""
Trader Stoikov-Avellaneda : optimal market making textbook.

Formules (Avellaneda-Stoikov 2008) :
  - s(t) = microprice actuel
  - q = position
  - γ = aversion au risque (param)
  - σ² = variance des returns (mesurée sur rolling window)
  - T-t = temps restant normalisé [0, 1]
  - k = intensité Poisson des trades (mesurée sur rolling window)

  reservation = s - q · γ · σ² · (T-t)
  spread_total = γ · σ² · (T-t) + (2/γ) · ln(1 + γ/k)
  bid = reservation - spread_total/2
  ask = reservation + spread_total/2

Pour Pepper (trending), on ajoute un drift estimé au reservation price.
"""
import json
import math
from typing import Dict, List, Optional, Tuple
from datamodel import Order, OrderDepth, TradingState


POSITION_LIMIT = 80
MAX_TS = 100_000  # durée simulation

# Params par produit
PRODUCT_PARAMS: Dict[str, dict] = {
    "ASH_COATED_OSMIUM": {
        "position_limit": 80,
        "gamma": 0.15,              # aversion au risque (plus élevé = spreads wider)
        "sigma_window": 50,         # fenêtre rolling pour variance
        "k_default": 1.5,           # intensité par défaut
        "k_window": 100,            # rolling window pour k
        "drift": 0.0,               # pas de trend sur Osmium
        "min_spread": 2,            # spread minimum en ticks (pour éviter cross)
        "max_spread": 20,           # cap spread
        "qty_per_side": 30,         # qty posée de chaque côté
        "use_microprice": True,
        # Inventory clearing agressif quand proche limit
        "clear_threshold_frac": 0.85,
    },
    "INTARIAN_PEPPER_ROOT": {
        "position_limit": 80,
        "gamma": 0.10,              # aversion plus faible (trend attendu)
        "sigma_window": 50,
        "k_default": 1.0,
        "k_window": 100,
        "drift": 1.0,               # Pepper trend ≈ +1/tick en live (0.00127/ts × 100 ticks step)
        "min_spread": 2,
        "max_spread": 20,
        "qty_per_side": 30,
        "use_microprice": True,
        "clear_threshold_frac": 0.85,
        # Bias directionnel : start long
        "target_bias": 40,
        "target_bias_decay_until": 0.97,
    },
}


def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _microprice(depth: OrderDepth) -> Optional[float]:
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bb is None or ba is None:
        return float(bb) if bb is not None else (float(ba) if ba is not None else None)
    bid_vol = depth.buy_orders.get(bb, 0)
    ask_vol = abs(depth.sell_orders.get(ba, 0))
    total = bid_vol + ask_vol
    if total == 0:
        return (bb + ba) / 2.0
    return (bb * ask_vol + ba * bid_vol) / total


def _mid(depth: OrderDepth) -> Optional[float]:
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bb is None or ba is None:
        return float(bb) if bb is not None else (float(ba) if ba is not None else None)
    return (bb + ba) / 2.0


def _estimate_sigma(prices: List[float], window: int) -> float:
    """Std des returns mid-to-mid sur rolling window."""
    if len(prices) < 2:
        return 1.0
    w = min(window, len(prices) - 1)
    returns = [prices[i] - prices[i - 1] for i in range(len(prices) - w, len(prices))]
    if not returns:
        return 1.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    return max(0.5, math.sqrt(max(0.01, var)))


def _estimate_k(trade_count_per_tick: List[int], window: int, default: float) -> float:
    """Intensité moyenne d'arrivée des trades."""
    if not trade_count_per_tick:
        return default
    w = min(window, len(trade_count_per_tick))
    recent = trade_count_per_tick[-w:]
    mean_count = sum(recent) / len(recent)
    return max(0.3, mean_count) if mean_count > 0 else default


def _clamp_qty(desired: int, current_pos: int, side: str, limit: int) -> int:
    if side == "BUY":
        return max(0, min(desired, limit - current_pos))
    return max(0, min(desired, limit + current_pos))


def trade_product(product: str, state: TradingState, trader_data: dict) -> List[Order]:
    params = PRODUCT_PARAMS[product]
    limit = int(params["position_limit"])
    depth = state.order_depths.get(product)
    if depth is None:
        return []
    orders: List[Order] = []

    # State
    pstate = trader_data.setdefault(product, {})
    prices = pstate.setdefault("prices", [])
    trade_counts = pstate.setdefault("trade_counts", [])

    # Current microprice / mid
    s = _microprice(depth) if params.get("use_microprice", True) else _mid(depth)
    if s is None:
        return []
    prices.append(float(s))
    if len(prices) > 500:
        prices[:] = prices[-500:]

    # Trade intensity update
    n_trades = len(state.market_trades.get(product, []) or [])
    trade_counts.append(n_trades)
    if len(trade_counts) > 500:
        trade_counts[:] = trade_counts[-500:]

    # Stoikov inputs
    gamma = float(params["gamma"])
    sigma = _estimate_sigma(prices, int(params["sigma_window"]))
    k = _estimate_k(trade_counts, int(params["k_window"]), float(params["k_default"]))
    T = float(MAX_TS)
    t = float(state.timestamp)
    time_left = max(0.0, (T - t) / T)  # [0, 1]

    position = state.position.get(product, 0)

    # Target bias (Pepper only)
    target_bias = 0
    if "target_bias" in params and time_left > 1.0 - float(params.get("target_bias_decay_until", 1.0)):
        target_bias = int(params["target_bias"])
    # q (inventory) ajusté par target_bias
    q = position - target_bias

    # Reservation price
    drift = float(params.get("drift", 0.0))
    reservation = s - q * gamma * sigma ** 2 * time_left + drift * (T - t) * 0.5  # forward drift
    # Note : on ajoute drift × temps_restant × 0.5 = gain attendu moyen futur (biais long)

    # Spread total
    log_arg = 1.0 + gamma / max(0.3, k)
    spread = gamma * sigma ** 2 * time_left + (2.0 / gamma) * math.log(log_arg)
    min_sp = int(params.get("min_spread", 2))
    max_sp = int(params.get("max_spread", 20))
    spread = max(min_sp, min(max_sp, spread))

    # Bid / Ask
    bid_price = int(round(reservation - spread / 2.0))
    ask_price = int(round(reservation + spread / 2.0))

    # Hard guard : ne pas crosser le book
    bb = _best_bid(depth)
    ba = _best_ask(depth)
    if ba is not None:
        bid_price = min(bid_price, ba - 1)
    if bb is not None:
        ask_price = max(ask_price, bb + 1)

    # Qty
    qty_side = int(params.get("qty_per_side", 30))
    clear_thresh = float(params.get("clear_threshold_frac", 0.85)) * limit

    # Inventory clearing : si |position| > clear_thresh, désactive le côté opposé et quote agressif l'autre
    if abs(position) > clear_thresh:
        if position > 0:
            # dump long : quote ask agressif au best_bid
            ask_price = bb + 0 if bb is not None else ask_price  # cross to clear
            ask_qty = _clamp_qty(min(qty_side, int(position - clear_thresh + 5)), position, "SELL", limit)
            if bb is not None:
                orders.append(Order(product, bb, -ask_qty))  # sell to best bid directly
            return orders
        else:
            bid_price = ba + 0 if ba is not None else bid_price
            bid_qty = _clamp_qty(min(qty_side, int(-position - clear_thresh + 5)), position, "BUY", limit)
            if ba is not None:
                orders.append(Order(product, ba, bid_qty))
            return orders

    # Post passive quotes
    buy_qty = _clamp_qty(qty_side, position, "BUY", limit)
    sell_qty = _clamp_qty(qty_side, position, "SELL", limit)

    if buy_qty > 0 and bid_price > 0:
        orders.append(Order(product, bid_price, buy_qty))
    if sell_qty > 0:
        orders.append(Order(product, ask_price, -sell_qty))

    # TAKE opportuniste : si le book offre mieux que notre bid/ask
    if ba is not None and ba < bid_price and buy_qty > 0:
        take_avail = -depth.sell_orders.get(ba, 0)
        take_qty = min(buy_qty, take_avail)
        if take_qty > 0:
            orders.append(Order(product, ba, take_qty))
    if bb is not None and bb > ask_price and sell_qty > 0:
        take_avail = depth.buy_orders.get(bb, 0)
        take_qty = min(sell_qty, take_avail)
        if take_qty > 0:
            orders.append(Order(product, bb, -take_qty))

    return orders


def _cap_gross_orders(orders: List[Order], limit: int) -> List[Order]:
    """Same safety cap as v31 to respect live strict rule."""
    capped = []
    buy_left = limit
    sell_left = limit
    for order in orders:
        if order.quantity > 0:
            qty = min(order.quantity, buy_left)
            buy_left -= qty
            if qty > 0:
                capped.append(Order(order.symbol, order.price, qty))
        elif order.quantity < 0:
            qty = min(-order.quantity, sell_left)
            sell_left -= qty
            if qty > 0:
                capped.append(Order(order.symbol, order.price, -qty))
    return capped


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}
        for product in state.order_depths.keys():
            try:
                orders = trade_product(product, state, trader_data)
                result[product] = _cap_gross_orders(orders, POSITION_LIMIT)
            except Exception as e:
                print(f"ERR Stoikov {state.timestamp} {product} {type(e).__name__}:{e}")
                result[product] = []

        try:
            out = json.dumps(trader_data, separators=(",", ":"))
            if len(out) > 49000:
                for _, pstate in trader_data.items():
                    if isinstance(pstate, dict):
                        for k in ("prices", "trade_counts"):
                            if k in pstate:
                                pstate[k] = pstate[k][-50:]
                out = json.dumps(trader_data, separators=(",", ":"))
        except Exception:
            out = ""
        return result, 0, out
