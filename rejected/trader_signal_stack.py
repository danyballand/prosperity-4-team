"""
Signal-stack taker — approche pure TAKE basee sur signaux multi-feature.
- Osm : copie v31 simplifiee (Kalman + spread capture)
- Pep : PAS de MAKE. Seulement TAKE quand signal compose positif.

Signaux Pep :
  S1 = OBI (Order Book Imbalance) : (bid_vol - ask_vol) / total
  S2 = microprice - mid : pression directionnelle
  S3 = momentum : prix_t - prix_{t-k}

Action : si S1+S2+S3 > threshold → BUY take. Si < -threshold → SELL take.
Position target = f(strength_signal) dans [-80, +80].
"""
import json
import math
from typing import Dict, List, Tuple
from datamodel import Order, OrderDepth, TradingState

POSITION_LIMIT = 80
MAX_TS = 100_000


def _best_bid(depth):
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth):
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _mid(depth):
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bb and ba:
        return (bb + ba) / 2.0
    return bb if bb else ba


def _microprice(depth):
    bb, ba = _best_bid(depth), _best_ask(depth)
    if not (bb and ba):
        return _mid(depth)
    bv = depth.buy_orders.get(bb, 0)
    av = abs(depth.sell_orders.get(ba, 0))
    total = bv + av
    return (bb * av + ba * bv) / total if total else (bb + ba) / 2.0


def _obi(depth):
    bb, ba = _best_bid(depth), _best_ask(depth)
    if not (bb and ba):
        return 0.0
    bv = sum(depth.buy_orders.values())
    av = sum(abs(v) for v in depth.sell_orders.values())
    total = bv + av
    return (bv - av) / total if total else 0.0


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            data = {}
        prices = data.setdefault("pep_prices", [])

        result: Dict[str, List[Order]] = {}

        # === OSMIUM : MAKE simple autour FV=10000 (reuse v31 idea) ===
        osm_depth = state.order_depths.get("ASH_COATED_OSMIUM")
        osm_orders = []
        if osm_depth is not None:
            pos = state.position.get("ASH_COATED_OSMIUM", 0)
            bb, ba = _best_bid(osm_depth), _best_ask(osm_depth)
            FV = 10000
            EDGE = 3
            bid_p = min(FV - EDGE, ba - 1) if ba else FV - EDGE
            ask_p = max(FV + EDGE, bb + 1) if bb else FV + EDGE
            bid_qty = max(0, min(30, POSITION_LIMIT - pos))
            ask_qty = max(0, min(30, POSITION_LIMIT + pos))
            if bid_qty > 0:
                osm_orders.append(Order("ASH_COATED_OSMIUM", int(bid_p), bid_qty))
            if ask_qty > 0:
                osm_orders.append(Order("ASH_COATED_OSMIUM", int(ask_p), -ask_qty))
            if ba and ba < FV and bid_qty > 0:
                take = min(bid_qty, -osm_depth.sell_orders.get(ba, 0))
                if take > 0:
                    osm_orders.append(Order("ASH_COATED_OSMIUM", ba, take))
            if bb and bb > FV and ask_qty > 0:
                take = min(ask_qty, osm_depth.buy_orders.get(bb, 0))
                if take > 0:
                    osm_orders.append(Order("ASH_COATED_OSMIUM", bb, -take))
        result["ASH_COATED_OSMIUM"] = osm_orders

        # === PEPPER : signal-stack taker ===
        pep_depth = state.order_depths.get("INTARIAN_PEPPER_ROOT")
        pep_orders = []
        if pep_depth is not None:
            pos = state.position.get("INTARIAN_PEPPER_ROOT", 0)
            bb, ba = _best_bid(pep_depth), _best_ask(pep_depth)
            mid = _mid(pep_depth)
            mp = _microprice(pep_depth)
            obi = _obi(pep_depth)

            if mid:
                prices.append(mid)
                if len(prices) > 50:
                    prices[:] = prices[-50:]

            # Signals
            s1 = obi                              # [-1, 1]
            s2 = (mp - mid) / 5.0 if mid else 0.0  # normalise
            s3 = 0.0
            if len(prices) >= 10:
                s3 = (prices[-1] - prices[-10]) / 5.0  # momentum normalise
            # Trend bias : on sait Pep trend +1/tick, donc ajouter bias const
            trend_bias = 0.5
            signal = s1 + s2 + s3 + trend_bias

            # Position target en fonction du signal
            target_pos = int(max(-POSITION_LIMIT, min(POSITION_LIMIT, signal * 80)))

            delta = target_pos - pos
            if delta > 0 and ba is not None:  # need BUY
                take_avail = -pep_depth.sell_orders.get(ba, 0)
                qty = min(delta, take_avail)
                if qty > 0:
                    pep_orders.append(Order("INTARIAN_PEPPER_ROOT", ba, qty))
            elif delta < 0 and bb is not None:  # need SELL
                take_avail = pep_depth.buy_orders.get(bb, 0)
                qty = min(-delta, take_avail)
                if qty > 0:
                    pep_orders.append(Order("INTARIAN_PEPPER_ROOT", bb, -qty))
        result["INTARIAN_PEPPER_ROOT"] = pep_orders

        try:
            out = json.dumps(data, separators=(",", ":"))
        except Exception:
            out = ""
        return result, 0, out
