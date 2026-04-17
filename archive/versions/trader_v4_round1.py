"""
IMC Prosperity 4 — Market Maker
Structure inspirée des Frankfurt Hedgehogs (P3), adaptée à l'API P4.

Pipeline par produit :
  1) fair value via "wall mid" (niveau bid/ask avec le plus gros volume)
  2) Phase TAKE  : sweep de tout ce qui est "gratuit" (< fv côté ask, > fv côté bid)
  3) Phase MAKE  : pose des quotes passifs à fv-1 / fv+1
  4) Inventory skew : décale les quotes selon la position, flatten si près de la limite
"""

from datamodel import OrderDepth, UserId, TradingState, Order
from typing import Dict, List, Tuple, Optional
import json
import statistics


# ----------------------------- Config ------------------------------------- #

POSITION_LIMIT = 80

# Produits Round 1
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]

# Paramètres par produit (override possible par produit si besoin)
DEFAULT_PARAMS = {
    "take_width": 0,          # on prend tout ce qui est strictement < fv (ask) / > fv (bid)
    "make_edge": 1,           # spread autour de la fv pour les quotes passifs
    "skew_ticks_per_unit": 0.05,  # on décale la quote de 1 tick tous les 20 en inventaire
    "flatten_threshold": 0.90,    # si |pos|/limit >= 0.9 on flatten à fv
    "max_history": 100,           # mids gardés dans traderData
    "min_wall_volume": 10,        # volume mini pour qu'un niveau compte comme "wall"
    "fixed_fv": None,             # si set, override le wall mid (pour produits stables)
}

PRODUCT_PARAMS: Dict[str, dict] = {
    # Produit stable : FV fixe à 10000 (découvert sur les 3 jours de data, std=5.3)
    "ASH_COATED_OSMIUM": {
        **DEFAULT_PARAMS,
        "fixed_fv": 10000,
        "make_edge": 2,         # quotes plus larges → plus de profit par fill passif
        "take_width": 1,        # ne prend que si ask < 9999 (vraies aubaines)
        "skew_ticks_per_unit": 0.04,
    },
    # Produit volatile/trending : on TAKE mais seulement si l'écart est > 3 (filtre le bruit).
    # Optimisé par sweep de paramètres : best = take_width=3, min_wall_volume=5 → +143k en backtest.
    "INTARIAN_PEPPER_ROOT": {
        **DEFAULT_PARAMS,
        "make_edge": 3,
        "skew_ticks_per_unit": 0.10,
        "min_wall_volume": 5,
        "flatten_threshold": 0.95,  # v4: on laisse la position grandir pour rider le trend
        "take_width": 3,
        "disable_take": False,
    },
    # Legacy (tutorial) -- garde au cas où
    "EMERALDS": dict(DEFAULT_PARAMS),
    "TOMATOES": dict(DEFAULT_PARAMS),
}


# ----------------------------- Helpers ------------------------------------ #

def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _wall_mid(depth: OrderDepth, min_vol: int) -> Optional[float]:
    """
    Fair value via 'wall mid' :
      - sur les bids, on prend le prix avec le plus gros volume (>= min_vol)
      - sur les asks idem (volume absolu)
      - fv = moyenne des deux
    Fallback : best bid / best ask mid. Fallback final : best price ou None.
    """
    bid_wall = None
    ask_wall = None

    if depth.buy_orders:
        # qty positives
        bid_wall = max(
            (p for p, q in depth.buy_orders.items() if q >= min_vol),
            key=lambda p: depth.buy_orders[p],
            default=None,
        )
    if depth.sell_orders:
        # qty négatives : on prend la plus grosse en valeur absolue
        ask_wall = min(
            (p for p, q in depth.sell_orders.items() if -q >= min_vol),
            key=lambda p: depth.sell_orders[p],  # le plus négatif = le plus gros volume
            default=None,
        )

    bb = _best_bid(depth)
    ba = _best_ask(depth)

    if bid_wall is None:
        bid_wall = bb
    if ask_wall is None:
        ask_wall = ba

    if bid_wall is not None and ask_wall is not None:
        return (bid_wall + ask_wall) / 2.0
    if bb is not None and ba is not None:
        return (bb + ba) / 2.0
    if bb is not None:
        return float(bb)
    if ba is not None:
        return float(ba)
    return None


def _clamp_order_qty(desired: int, current_pos: int, side: str) -> int:
    """
    Renvoie la quantité autorisée (en valeur absolue) pour ne pas dépasser la position limit,
    en tenant compte des ordres déjà cumulés sur ce côté.
    side: 'BUY' ou 'SELL'
    """
    if side == "BUY":
        room = POSITION_LIMIT - current_pos
        return max(0, min(desired, room))
    else:
        room = POSITION_LIMIT + current_pos  # current_pos peut être négatif
        return max(0, min(desired, room))


# ----------------------------- Core strategy ------------------------------ #

def trade_product(
    product: str,
    state: TradingState,
    trader_data: dict,
) -> List[Order]:
    """
    Stratégie générique take + make avec skew inventaire.
    """
    params = PRODUCT_PARAMS.get(product, DEFAULT_PARAMS)
    orders: List[Order] = []

    depth = state.order_depths.get(product)
    if depth is None:
        return orders

    position = state.position.get(product, 0)
    # Si on a une fair value fixe, on l'utilise. Sinon wall mid dynamique.
    if params.get("fixed_fv") is not None:
        fv = float(params["fixed_fv"])
    else:
        fv = _wall_mid(depth, params["min_wall_volume"])
    if fv is None:
        return orders

    # --- Inventory skew -----------------------------------------------------
    # Décalage proportionnel à l'inventaire (en ticks).
    skew = -position * params["skew_ticks_per_unit"]  # long => on baisse nos quotes
    fv_bid_ref = fv + skew
    fv_ask_ref = fv + skew

    # Flatten si trop proche de la limite : on agresse vers le milieu
    near_limit = abs(position) >= params["flatten_threshold"] * POSITION_LIMIT

    bb = _best_bid(depth)
    ba = _best_ask(depth)

    # --- Phase 1 : TAKE -----------------------------------------------------
    # On achète tous les asks < fv (ou <= fv si on flatten vers le haut parce que short)
    take_buy_threshold = fv - params["take_width"]
    take_sell_threshold = fv + params["take_width"]
    if near_limit and position < 0:
        take_buy_threshold = fv  # on va jusqu'à fv inclus pour se rapprocher de 0
    if near_limit and position > 0:
        take_sell_threshold = fv

    buy_used = 0
    sell_used = 0

    disable_take = params.get("disable_take", False)

    if not disable_take:
        # asks triés du moins cher au plus cher
        for ask_price in sorted(depth.sell_orders.keys()):
            ask_qty = -depth.sell_orders[ask_price]
            if ask_price < take_buy_threshold or (near_limit and position < 0 and ask_price <= take_buy_threshold):
                qty = _clamp_order_qty(ask_qty, position + buy_used, "BUY")
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    buy_used += qty
            else:
                break

        # bids triés du plus cher au moins cher
        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            bid_qty = depth.buy_orders[bid_price]
            if bid_price > take_sell_threshold or (near_limit and position > 0 and bid_price >= take_sell_threshold):
                qty = _clamp_order_qty(bid_qty, position - sell_used, "SELL")
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    sell_used += qty
            else:
                break

    # --- Phase 2 : MAKE -----------------------------------------------------
    if not near_limit:
        edge = params["make_edge"]
        make_bid_price = int(round(fv_bid_ref - edge))
        make_ask_price = int(round(fv_ask_ref + edge))

        # ne jamais croiser le marché existant
        if ba is not None:
            make_bid_price = min(make_bid_price, ba - 1)
        if bb is not None:
            make_ask_price = max(make_ask_price, bb + 1)

        remaining_buy = POSITION_LIMIT - (position + buy_used)
        remaining_sell = POSITION_LIMIT + (position - sell_used)

        if remaining_buy > 0 and make_bid_price > 0:
            orders.append(Order(product, make_bid_price, remaining_buy))
        if remaining_sell > 0:
            orders.append(Order(product, make_ask_price, -remaining_sell))

    # --- Logging ------------------------------------------------------------
    print(
        f"t={state.timestamp} {product} fv={fv:.2f} pos={position} "
        f"bb={bb} ba={ba} orders={[(o.price, o.quantity) for o in orders]}"
    )

    # --- Mémoire persistante -----------------------------------------------
    pstate = trader_data.setdefault(product, {})
    mids = pstate.setdefault("mids", [])
    mids.append(fv)
    if len(mids) > params["max_history"]:
        del mids[: len(mids) - params["max_history"]]

    pstate["min"] = min(pstate.get("min", fv), fv)
    pstate["max"] = max(pstate.get("max", fv), fv)

    # Compteur de trades par taille (détection de patterns type "Olivia")
    size_counter = pstate.setdefault("trade_size_counts", {})
    for tr in state.market_trades.get(product, []) or []:
        key = str(abs(tr.quantity))
        size_counter[key] = size_counter.get(key, 0) + 1
    for tr in state.own_trades.get(product, []) or []:
        key = str(abs(tr.quantity))
        size_counter[key] = size_counter.get(key, 0) + 1

    return orders


# ----------------------------- Trader class ------------------------------- #

class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        # Charge la mémoire
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}

        # Boucle sur tous les produits listés dans order_depths (plus robuste que PRODUCTS en dur)
        for product in state.order_depths.keys():
            try:
                result[product] = trade_product(product, state, trader_data)
            except Exception as e:
                print(f"ERROR on {product} t={state.timestamp}: {e}")
                result[product] = []

        # Sérialise la mémoire (borne à 50k chars)
        try:
            out = json.dumps(trader_data, separators=(",", ":"))
            if len(out) > 49000:
                # Trim agressif : on garde les 50 derniers mids par produit
                for p, pstate in trader_data.items():
                    if "mids" in pstate:
                        pstate["mids"] = pstate["mids"][-50:]
                out = json.dumps(trader_data, separators=(",", ":"))
        except Exception:
            out = ""

        return result, 0, out

    def bid(self) -> int:
        # Placeholder pour le Round 2 algo de Prosperity
        return 0
