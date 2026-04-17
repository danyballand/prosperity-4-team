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
        "make_edge": 20,
        "take_width": 15,       # v15 final : optimal backtest
        "skew_ticks_per_unit": 0.04,
        "double_edge": True,
        "inventory_clearing": True,
        "clearing_threshold": 0.1,  # v15 : clearing plus tôt (était 0.3)
        "pennying": True,
        "min_pennying_edge": 1,
    },
    # Produit volatile/trending : on TAKE mais seulement si l'écart est > 3 (filtre le bruit).
    # Optimisé par sweep de paramètres : best = take_width=3, min_wall_volume=5 → +143k en backtest.
    "INTARIAN_PEPPER_ROOT": {
        **DEFAULT_PARAMS,
        "make_edge": 3,
        "skew_ticks_per_unit": 0.10,
        "min_wall_volume": 5,
        "flatten_threshold": 0.95,  # v4
        "take_width": 3,
        "disable_take": False,
        "mr_enabled": False,
        "time_adaptive_bias": True,
        "max_bias": 30,
        "inventory_clearing": False,
        # v14 : Kalman drift=2.5, R=200 (meilleur combo du sweep final)
        "use_kalman": True,
        "kalman_drift": 2.5,
        "kalman_Q": 0.25,
        "kalman_R": 200.0,
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


def _kalman_fair(product: str, depth: OrderDepth, params: dict, trader_data: dict) -> Optional[float]:
    """
    Filtre de Kalman univarié avec drift pour estimer le vrai prix caché.

    Modèle :
      État        : x_t = x_{t-1} + drift + w_t,  w_t ~ N(0, Q)
      Observation : z_t = x_t + v_t,              v_t ~ N(0, R)

    Inspiration : rapport P4 recommande KF pour séparer drift linéaire du bruit
    haute fréquence (autocorr -0.5 sur diffs).
    """
    # Observation = wall_mid (moins bruité que best bid/ask mid)
    z = _wall_mid(depth, params.get("min_wall_volume", 5))
    if z is None:
        return None

    pstate = trader_data.setdefault(product, {})
    kf = pstate.get("kf", None)
    drift = params.get("kalman_drift", 0.1)      # +0.1 par tick mesuré sur Pepper
    Q = params.get("kalman_Q", 0.25)             # variance processus (petit = smooth)
    R = params.get("kalman_R", 4.0)              # variance observation (grand = ignore bruit)

    if kf is None:
        # init : on démarre sur l'observation avec grande incertitude
        kf = {"x": z, "P": 100.0}

    # Predict
    x_pred = kf["x"] + drift
    P_pred = kf["P"] + Q

    # Update
    K = P_pred / (P_pred + R)  # Kalman gain
    kf["x"] = x_pred + K * (z - x_pred)
    kf["P"] = (1 - K) * P_pred

    pstate["kf"] = kf
    return kf["x"]


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
    # Si on a une fair value fixe, on l'utilise. Sinon wall mid dynamique ou Kalman.
    if params.get("fixed_fv") is not None:
        fv = float(params["fixed_fv"])
    elif params.get("use_kalman", False):
        fv = _kalman_fair(product, depth, params, trader_data)
    else:
        fv = _wall_mid(depth, params["min_wall_volume"])
    if fv is None:
        return orders

    # --- Biais structurel adaptatif (v6) -----------------------------------
    # Si target_long_bias est défini, on skew le point de référence des quotes
    # vers le haut en début de journée (accumulation) et on flatten en fin.
    # state.timestamp va de 0 à 999_900 sur un run typique.
    target_bias = 0
    if params.get("time_adaptive_bias", False):
        max_ts = 1_000_000
        ts = state.timestamp
        day_progress = min(1.0, ts / max_ts)
        max_bias = params.get("max_bias", 30)  # biais long max en début
        # En U inversé : 0 au début, max au milieu, 0 à la fin (pour capturer
        # l'accumulation durant le trend puis le relâchement)
        # Ici pepper trend tout le run donc on utilise une décroissance linéaire.
        target_bias = int(max_bias * (1 - day_progress))

    # --- Inventory skew -----------------------------------------------------
    # Le skew pousse la position vers target_bias (au lieu de 0 par défaut).
    skew = -(position - target_bias) * params["skew_ticks_per_unit"]
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

    # --- Phase 1bis : INVENTORY CLEARING 0-EV (Linear Utility trick) -------
    # Si on est proche de la limite et qu'il y a de la liquidité AU fair value,
    # on débloque la position même à profit nul (libérer la limite pour les
    # vraies opportunités futures vaut plus que ne rien faire).
    clearing_enabled = params.get("inventory_clearing", False)
    if clearing_enabled:
        cur_pos = position + buy_used - sell_used
        clearing_threshold = params.get("clearing_threshold", 0.5) * POSITION_LIMIT
        if cur_pos > clearing_threshold:
            # on est long → on essaye de vendre AU fair (ou juste au-dessus)
            fv_round = int(round(fv))
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_price >= fv_round:  # on accepte de vendre à fv+ (EV>=0)
                    qty = _clamp_order_qty(depth.buy_orders[bid_price],
                                           position - sell_used, "SELL")
                    if qty > 0:
                        orders.append(Order(product, bid_price, -qty))
                        sell_used += qty
                    if cur_pos - sell_used <= clearing_threshold:
                        break
                else:
                    break
        elif cur_pos < -clearing_threshold:
            # short → on achète au fair pour libérer
            fv_round = int(round(fv))
            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price <= fv_round:
                    qty = _clamp_order_qty(-depth.sell_orders[ask_price],
                                           position + buy_used, "BUY")
                    if qty > 0:
                        orders.append(Order(product, ask_price, qty))
                        buy_used += qty
                    if cur_pos + buy_used >= -clearing_threshold:
                        break
                else:
                    break

    # --- Phase 2 : MAKE -----------------------------------------------------
    if not near_limit:
        edge = params["make_edge"]
        make_bid_price = int(round(fv_bid_ref - edge))
        make_ask_price = int(round(fv_ask_ref + edge))

        # --- PENNYING DYNAMIQUE (v9, Frankfurt Hedgehogs + Linear Utility) ---
        # On se place 1 tick mieux que le meilleur niveau externe du book,
        # tant qu'on garde une edge minimale par rapport à la FV.
        # min_edge = profit minimum accepté par quote.
        if params.get("pennying", False):
            min_edge = params.get("min_pennying_edge", 1)
            # Côté bid : on overbid le meilleur bid existant (+1 tick au-dessus)
            if bb is not None:
                penny_bid = bb + 1
                # Mais on refuse de bider au-dessus de fv - min_edge
                penny_bid = min(penny_bid, int(fv) - min_edge)
                # On prend le plus haut des deux (plus proche du fv)
                make_bid_price = max(make_bid_price, penny_bid)
            # Côté ask : on undercut le meilleur ask existant (-1 tick en dessous)
            if ba is not None:
                penny_ask = ba - 1
                # Mais on refuse de vendre en dessous de fv + min_edge
                penny_ask = max(penny_ask, int(fv) + min_edge)
                make_ask_price = min(make_ask_price, penny_ask)

        # ne jamais croiser le marché existant
        if ba is not None:
            make_bid_price = min(make_bid_price, ba - 1)
        if bb is not None:
            make_ask_price = max(make_ask_price, bb + 1)

        remaining_buy = POSITION_LIMIT - (position + buy_used)
        remaining_sell = POSITION_LIMIT + (position - sell_used)

        # Double-edge : 2 niveaux de quotes (ex Osmium : 9998+9997 et 10002+10003)
        double_edge = params.get("double_edge", False)
        if double_edge and remaining_buy >= 2 and remaining_sell >= 2:
            # On répartit 60/40 entre les 2 niveaux
            half_buy = remaining_buy // 2
            half_sell = remaining_sell // 2
            if make_bid_price - 1 > 0:
                orders.append(Order(product, make_bid_price, remaining_buy - half_buy))
                orders.append(Order(product, make_bid_price - 1, half_buy))
            if make_ask_price >= 1:
                orders.append(Order(product, make_ask_price, -(remaining_sell - half_sell)))
                orders.append(Order(product, make_ask_price + 1, -half_sell))
        else:
            if remaining_buy > 0 and make_bid_price > 0:
                orders.append(Order(product, make_bid_price, remaining_buy))
            if remaining_sell > 0:
                orders.append(Order(product, make_ask_price, -remaining_sell))

    # --- Mémoire persistante (avant MR overlay car on en a besoin) ---------
    pstate = trader_data.setdefault(product, {})
    mids = pstate.setdefault("mids", [])
    prev_fv = mids[-1] if mids else fv
    mids.append(fv)
    if len(mids) > params["max_history"]:
        del mids[: len(mids) - params["max_history"]]

    # --- Phase 3 : MEAN REVERSION sur diffs (tail de distribution) ---------
    # Seulement activé sur Pepper (flag mr_enabled). On regarde le dernier diff
    # et si il est statistiquement extrême (>2 sigma des diffs récents), on parie
    # sur un retour (l'autocorr des diffs vaut -0.5 sur Pepper).
    if params.get("mr_enabled", False) and len(mids) >= 20:
        # Diffs sur les 20 derniers ticks
        diffs = [mids[i] - mids[i - 1] for i in range(-19, 0)]
        mean_d = sum(diffs) / len(diffs)
        var_d = sum((d - mean_d) ** 2 for d in diffs) / len(diffs)
        import math as _m
        std_d = _m.sqrt(var_d) if var_d > 0 else 0
        last_diff = fv - prev_fv
        if std_d > 0:
            z_diff = (last_diff - mean_d) / std_d
            # Seuil tail : |z| > 2 → mouvement anormalement grand
            MR_Z_THRESHOLD = 2.0
            MR_SIZE = params.get("mr_size", 10)
            if z_diff > MR_Z_THRESHOLD and bb is not None:
                # Le prix vient de sauter anormalement haut → on parie baisse → SELL
                qty = _clamp_order_qty(min(MR_SIZE, depth.buy_orders.get(bb, 0)),
                                       position - sell_used, "SELL")
                if qty > 0:
                    orders.append(Order(product, bb, -qty))
                    sell_used += qty
            elif z_diff < -MR_Z_THRESHOLD and ba is not None:
                # Chute anormale → BUY
                qty = _clamp_order_qty(min(MR_SIZE, -depth.sell_orders.get(ba, 0)),
                                       position + buy_used, "BUY")
                if qty > 0:
                    orders.append(Order(product, ba, qty))
                    buy_used += qty

    # --- Logging ------------------------------------------------------------
    print(
        f"t={state.timestamp} {product} fv={fv:.2f} pos={position} "
        f"bb={bb} ba={ba} orders={[(o.price, o.quantity) for o in orders]}"
    )

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
