"""
IMC Prosperity 4 — Round 1
v10 : Stratégie hybride
  - OSMIUM : market maker avec take + double edge + inventory clearing (v8/v9 qui marche)
  - PEPPER : DIRECTIONAL TRADER qui accumule long rapidement sur le trend
             (inspiration : top teams P3 sur Kelp+drift, Linear Utility)
"""

from datamodel import OrderDepth, UserId, TradingState, Order
from typing import Dict, List, Tuple, Optional
import json

POSITION_LIMIT = 80


# ----------------------------- Helpers ------------------------------------ #

def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _wall_mid(depth: OrderDepth, min_vol: int = 5) -> Optional[float]:
    bid_wall = ask_wall = None
    if depth.buy_orders:
        bid_wall = max(
            (p for p, q in depth.buy_orders.items() if q >= min_vol),
            key=lambda p: depth.buy_orders[p], default=None)
    if depth.sell_orders:
        ask_wall = min(
            (p for p, q in depth.sell_orders.items() if -q >= min_vol),
            key=lambda p: depth.sell_orders[p], default=None)
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bid_wall is None: bid_wall = bb
    if ask_wall is None: ask_wall = ba
    if bid_wall is not None and ask_wall is not None:
        return (bid_wall + ask_wall) / 2.0
    if bb is not None and ba is not None:
        return (bb + ba) / 2.0
    return float(bb) if bb is not None else (float(ba) if ba is not None else None)


def _clamp(qty: int, current_pos: int, side: str) -> int:
    if side == "BUY":
        return max(0, min(qty, POSITION_LIMIT - current_pos))
    return max(0, min(qty, POSITION_LIMIT + current_pos))


# ============================================================================
#                              OSMIUM (market maker)
# ============================================================================

FV_OSMIUM = 10000
OSM_TAKE_WIDTH = 1
OSM_MAKE_EDGE = 2
OSM_SKEW = 0.04
OSM_CLEARING_THRESHOLD = 0.3  # flatten à EV=0 si |pos| > 24


def trade_osmium(state: TradingState, trader_data: dict) -> List[Order]:
    p = "ASH_COATED_OSMIUM"
    depth = state.order_depths.get(p)
    if depth is None: return []
    pos = state.position.get(p, 0)
    orders: List[Order] = []
    buy_used = sell_used = 0
    fv = FV_OSMIUM
    bb, ba = _best_bid(depth), _best_ask(depth)

    # Phase 1 : TAKE
    for ask in sorted(depth.sell_orders.keys()):
        if ask < fv - OSM_TAKE_WIDTH:
            q = _clamp(-depth.sell_orders[ask], pos + buy_used, "BUY")
            if q > 0:
                orders.append(Order(p, ask, q)); buy_used += q
        else: break
    for bid in sorted(depth.buy_orders.keys(), reverse=True):
        if bid > fv + OSM_TAKE_WIDTH:
            q = _clamp(depth.buy_orders[bid], pos - sell_used, "SELL")
            if q > 0:
                orders.append(Order(p, bid, -q)); sell_used += q
        else: break

    # Phase 1bis : CLEARING 0-EV (libère la limite)
    cur = pos + buy_used - sell_used
    if cur > OSM_CLEARING_THRESHOLD * POSITION_LIMIT:
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid >= fv:
                q = _clamp(depth.buy_orders[bid], pos - sell_used, "SELL")
                if q > 0:
                    orders.append(Order(p, bid, -q)); sell_used += q
                if cur - sell_used <= OSM_CLEARING_THRESHOLD * POSITION_LIMIT: break
            else: break
    elif cur < -OSM_CLEARING_THRESHOLD * POSITION_LIMIT:
        for ask in sorted(depth.sell_orders.keys()):
            if ask <= fv:
                q = _clamp(-depth.sell_orders[ask], pos + buy_used, "BUY")
                if q > 0:
                    orders.append(Order(p, ask, q)); buy_used += q
                if cur + buy_used >= -OSM_CLEARING_THRESHOLD * POSITION_LIMIT: break
            else: break

    # Phase 2 : MAKE (double edge)
    skew = -pos * OSM_SKEW
    bid_px = int(round(fv + skew - OSM_MAKE_EDGE))
    ask_px = int(round(fv + skew + OSM_MAKE_EDGE))
    if ba is not None: bid_px = min(bid_px, ba - 1)
    if bb is not None: ask_px = max(ask_px, bb + 1)
    rb = POSITION_LIMIT - (pos + buy_used)
    rs = POSITION_LIMIT + (pos - sell_used)
    if rb >= 2:
        h = rb // 2
        orders.append(Order(p, bid_px, rb - h))
        orders.append(Order(p, bid_px - 1, h))
    elif rb > 0:
        orders.append(Order(p, bid_px, rb))
    if rs >= 2:
        h = rs // 2
        orders.append(Order(p, ask_px, -(rs - h)))
        orders.append(Order(p, ask_px + 1, -h))
    elif rs > 0:
        orders.append(Order(p, ask_px, -rs))

    print(f"t={state.timestamp} OSM fv={fv} pos={pos} orders={[(o.price,o.quantity) for o in orders]}")
    return orders


# ============================================================================
#                   PEPPER ROOT (directional + adaptive)
# ============================================================================
#
# Stratégie : Pepper trend +1000/jour de manière quasi-déterministe.
# On ACCUMULE LONG rapidement (jusqu'à POSITION_LIMIT) et on RIDE LE TREND.
# Sortie progressive en fin de journée.
#
# Modules :
#  - fair value = wall_mid + EMA short correction
#  - position target = fonction du temps (agressif long début/milieu, flatten fin)
#  - take directionnel : on achète activement à l'ask si on est sous target
#  - make : on quote autour de la fair, asymétrique (favorise buy)
#  - micro-MR : seulement pour améliorer l'exécution, pas pour le signal principal

PEPPER_DRIFT_PER_TICK = 0.10           # +1000 sur 10000 ticks mesuré
PEPPER_EMA_ALPHA = 0.10                # lissage du wall mid
PEPPER_MAKE_EDGE = 2                   # plus agressif qu'avant (était 3)
PEPPER_TAKE_THRESHOLD_FAIR = 2         # take si ask < fair - 2 ou bid > fair + 2


def _pepper_target_position(ts: int) -> int:
    """
    Target de position sur pepper en fonction du timestamp.
    0→10% du run : accumule rapidement à +80 (max long)
    10→70% : on reste à +80 (on ride le trend)
    70→95% : décroît linéairement de +80 à +20
    95→100% : flatten à 0
    """
    progress = ts / 1_000_000
    if progress < 0.10:
        return int(POSITION_LIMIT * progress / 0.10)  # 0 → 80
    if progress < 0.70:
        return POSITION_LIMIT  # 80 plein trend
    if progress < 0.95:
        # 80 → 20
        p = (progress - 0.70) / 0.25
        return int(POSITION_LIMIT - p * (POSITION_LIMIT - 20))
    # 20 → 0
    p = (progress - 0.95) / 0.05
    return int(20 * (1 - p))


def trade_pepper(state: TradingState, trader_data: dict) -> List[Order]:
    p = "INTARIAN_PEPPER_ROOT"
    depth = state.order_depths.get(p)
    if depth is None: return []
    pos = state.position.get(p, 0)
    orders: List[Order] = []
    buy_used = sell_used = 0
    bb, ba = _best_bid(depth), _best_ask(depth)

    # Fair value = EMA du wall_mid (lissé)
    wm = _wall_mid(depth, 5)
    if wm is None: return []
    pstate = trader_data.setdefault(p, {})
    ema = pstate.get("ema_fair", wm)
    ema = (1 - PEPPER_EMA_ALPHA) * ema + PEPPER_EMA_ALPHA * wm
    pstate["ema_fair"] = ema
    fair = ema  # fair utilisée pour décisions

    # Position cible selon le temps
    target = _pepper_target_position(state.timestamp)

    # --- Phase 1 : Push vers target_position via TAKE actif ---------------
    # Si on est en dessous du target, on achète agressivement.
    # On accepte de payer jusqu'à fair + PEPPER_TAKE_THRESHOLD_FAIR pour remonter.
    need_buy = target - pos
    if need_buy > 0 and ba is not None:
        for ask in sorted(depth.sell_orders.keys()):
            # on accepte jusqu'à fair + 1 (on veut remplir la target)
            if ask <= fair + 1:
                q = _clamp(min(need_buy - buy_used + sell_used,
                               -depth.sell_orders[ask]),
                           pos + buy_used, "BUY")
                if q > 0:
                    orders.append(Order(p, ask, q)); buy_used += q
                if buy_used >= need_buy: break
            else: break

    # Si on est au-dessus du target, on vend
    need_sell = pos - target
    if need_sell > 0 and bb is not None:
        for bid in sorted(depth.buy_orders.keys(), reverse=True):
            if bid >= fair - 1:
                q = _clamp(min(need_sell - sell_used + buy_used,
                               depth.buy_orders[bid]),
                           pos - sell_used, "SELL")
                if q > 0:
                    orders.append(Order(p, bid, -q)); sell_used += q
                if sell_used >= need_sell: break
            else: break

    # --- Phase 2 : TAKE opportuniste sur gros écarts ----------------------
    # Si l'ask est bien en dessous de fair, on rafle quelle que soit la position
    for ask in sorted(depth.sell_orders.keys()):
        if ask < fair - PEPPER_TAKE_THRESHOLD_FAIR:
            q = _clamp(-depth.sell_orders[ask], pos + buy_used, "BUY")
            if q > 0:
                orders.append(Order(p, ask, q)); buy_used += q
        else: break
    for bid in sorted(depth.buy_orders.keys(), reverse=True):
        if bid > fair + PEPPER_TAKE_THRESHOLD_FAIR:
            q = _clamp(depth.buy_orders[bid], pos - sell_used, "SELL")
            if q > 0:
                orders.append(Order(p, bid, -q)); sell_used += q
        else: break

    # --- Phase 3 : MAKE passif autour de fair ------------------------------
    # Asymétrique : bid plus proche pour favoriser les achats (on veut rester long)
    cur = pos + buy_used - sell_used
    # Si on est en dessous du target → bid agressif, ask large
    # Si au-dessus → bid large, ask agressif
    if cur < target:
        bid_edge = 1
        ask_edge = 4
    elif cur > target:
        bid_edge = 4
        ask_edge = 1
    else:
        bid_edge = ask_edge = PEPPER_MAKE_EDGE

    make_bid = int(round(fair - bid_edge))
    make_ask = int(round(fair + ask_edge))
    if ba is not None: make_bid = min(make_bid, ba - 1)
    if bb is not None: make_ask = max(make_ask, bb + 1)
    rb = POSITION_LIMIT - (pos + buy_used)
    rs = POSITION_LIMIT + (pos - sell_used)
    if rb > 0: orders.append(Order(p, make_bid, rb))
    if rs > 0: orders.append(Order(p, make_ask, -rs))

    print(f"t={state.timestamp} PEP fv={fair:.1f} pos={pos} tgt={target} orders={[(o.price,o.quantity) for o in orders]}")
    return orders


# ----------------------------- Trader class ------------------------------- #

class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}
        try:
            result["ASH_COATED_OSMIUM"] = trade_osmium(state, trader_data)
        except Exception as e:
            print(f"ERR OSM t={state.timestamp}: {e}")
            result["ASH_COATED_OSMIUM"] = []
        try:
            result["INTARIAN_PEPPER_ROOT"] = trade_pepper(state, trader_data)
        except Exception as e:
            print(f"ERR PEP t={state.timestamp}: {e}")
            result["INTARIAN_PEPPER_ROOT"] = []

        try:
            out = json.dumps(trader_data, separators=(",", ":"))
        except Exception:
            out = ""
        return result, 0, out

    def bid(self) -> int:
        return 0
