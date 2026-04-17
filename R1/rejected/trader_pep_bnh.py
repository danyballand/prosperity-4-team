"""
Pure Buy-and-Hold sur Pepper (trend +1000/jour).
- Osm : copié de v31 (Kalman optimal)
- Pep : TAKE 80 immédiatement au best_ask, HOLD, sell 80 au best_bid en fin

Test conceptuel : la théorie dit que si Pep trend +1000/jour, HOLD 80 tout le jour
donnerait 80 * delta_price_end_start. On vérifie empiriquement.
"""
import json
from typing import Dict, List, Tuple
from datamodel import Order, OrderDepth, TradingState

# Import v31 pour Osm (on réutilise la logique Kalman existante)
# On va juste hack : redéfinir Trader.run avec logique custom sur Pep

POSITION_LIMIT = 80
MAX_TS = 100_000
SELL_START_TS = 95_000  # à partir de ts=95k, on commence à unwind


def _best_bid(depth):
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth):
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}

        # === OSMIUM : stratégie simple autour de FV=10000 ===
        osm_depth = state.order_depths.get("ASH_COATED_OSMIUM")
        osm_orders = []
        if osm_depth is not None:
            pos = state.position.get("ASH_COATED_OSMIUM", 0)
            bb = _best_bid(osm_depth)
            ba = _best_ask(osm_depth)
            FV = 10000
            EDGE = 3
            # MAKE quotes autour de FV
            if ba is not None and ba - 1 > FV - EDGE:
                bid_p = FV - EDGE
            else:
                bid_p = bb + 1 if bb is not None else FV - EDGE
            if bb is not None and bb + 1 < FV + EDGE:
                ask_p = FV + EDGE
            else:
                ask_p = ba - 1 if ba is not None else FV + EDGE
            bid_qty = max(0, min(30, POSITION_LIMIT - pos))
            ask_qty = max(0, min(30, POSITION_LIMIT + pos))
            if bid_qty > 0:
                osm_orders.append(Order("ASH_COATED_OSMIUM", int(bid_p), bid_qty))
            if ask_qty > 0:
                osm_orders.append(Order("ASH_COATED_OSMIUM", int(ask_p), -ask_qty))
            # TAKE si ba < FV (underpriced)
            if ba is not None and ba < FV and bid_qty > 0:
                take_avail = -osm_depth.sell_orders.get(ba, 0)
                take_qty = min(bid_qty, take_avail)
                if take_qty > 0:
                    osm_orders.append(Order("ASH_COATED_OSMIUM", ba, take_qty))
            if bb is not None and bb > FV and ask_qty > 0:
                take_avail = osm_depth.buy_orders.get(bb, 0)
                take_qty = min(ask_qty, take_avail)
                if take_qty > 0:
                    osm_orders.append(Order("ASH_COATED_OSMIUM", bb, -take_qty))
        result["ASH_COATED_OSMIUM"] = osm_orders

        # === PEPPER : pure buy-and-hold ===
        pep_depth = state.order_depths.get("INTARIAN_PEPPER_ROOT")
        pep_orders = []
        if pep_depth is not None:
            pos = state.position.get("INTARIAN_PEPPER_ROOT", 0)
            ba = _best_ask(pep_depth)
            bb = _best_bid(pep_depth)
            t = state.timestamp

            if t < SELL_START_TS:
                # RAMP UP : vise position +80
                if pos < POSITION_LIMIT and ba is not None:
                    want = POSITION_LIMIT - pos
                    take_avail = -pep_depth.sell_orders.get(ba, 0)
                    qty = min(want, take_avail)
                    if qty > 0:
                        pep_orders.append(Order("INTARIAN_PEPPER_ROOT", ba, qty))
                    # Aussi poster un buy au mid+1 pour MAKE
                    if bb is not None and want > qty:
                        bid_price = bb + 1
                        remain = want - qty
                        pep_orders.append(Order("INTARIAN_PEPPER_ROOT", bid_price, min(remain, 30)))
            else:
                # UNWIND : sell position
                if pos > 0 and bb is not None:
                    take_avail = pep_depth.buy_orders.get(bb, 0)
                    qty = min(pos, take_avail)
                    if qty > 0:
                        pep_orders.append(Order("INTARIAN_PEPPER_ROOT", bb, -qty))
                    if ba is not None and pos > qty:
                        ask_price = ba - 1
                        remain = pos - qty
                        pep_orders.append(Order("INTARIAN_PEPPER_ROOT", ask_price, -min(remain, 30)))
        result["INTARIAN_PEPPER_ROOT"] = pep_orders

        return result, 0, ""
