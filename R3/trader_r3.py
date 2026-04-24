"""
IMC Prosperity 4 Round 1 — v16
Base : code du pote (triple_edge, trend_guard, bootstrap_entry, kalman)
Ajouts :
  - Volume-weighted microprice (fair value Pepper améliorée)
  - Order Book Imbalance (OBI) pour skew directionnel Osmium
  - Informed trader detector LIVE-ONLY (safe en backtest)
"""
import json
import math
from typing import Dict, List, Optional, Tuple
from datamodel import Order, OrderDepth, TradingState

# R3 : modules options (BS pricing + IV surface fit + Z-score scalping)
try:
    from bs_pricing import call_price, implied_vol, delta as bs_delta, vega as bs_vega
    from iv_surface import fit_quadratic, evaluate_surface, IVSurfaceTracker
    _OPTIONS_MODULES_OK = True
except ImportError:
    _OPTIONS_MODULES_OK = False

# =====================  SCALPING CONFIG  =====================
# Testé : backtest A+B donne +32,986 vs A seul +33,036 (-50 SS noise).
# Le signal Codex +1.43 ticks/trade existe mais nécessite exit non-aggressive
# qui est impossible sur 5400 (flux 100% at-bid = personne ne lève l'ask).
# Désactivé par défaut, code conservé pour itération R3 day 2/3.
ENABLE_VEV_5400_SCALPING = False  # flag A/B : True = scalping actif
SCALP_TARGET_STRIKE = 5400
SCALP_POS_CAP = 150               # half of limit 300
SCALP_Z_ENTRY = -2.0              # buy when Z < entry
SCALP_Z_EXIT  = 0.0               # sell when Z > exit
SCALP_Z_KILL  = 2.5               # flatten aggressive if Z > kill
SCALP_TTE_DAYS = 5                # live R3 : TTE = 5d
SCALP_TRADING_DAYS_YEAR = 250
SCALP_MIN_IV_POINTS = 5           # min strikes pour fit quadratique


POSITION_LIMIT = 80

DEFAULT_PARAMS = {
    "position_limit": 80,
    "take_width": 0,
    "make_edge": 1,
    "skew_ticks_per_unit": 0.05,
    "flatten_threshold": 0.90,
    "max_history": 100,
    "min_wall_volume": 10,
    "fixed_fv": None,
}

PRODUCT_PARAMS: Dict[str, dict] = {
    "ASH_COATED_OSMIUM": {
        **DEFAULT_PARAMS,
        "position_limit": 80,
        "fixed_fv": 10000,
        "take_width": 0,
        "inventory_aware_take": True,
        "take_skew_multiplier": 2.0,
        "make_edge": 97,      # v31 : pic entre 95 (+85) et 100 (−1197). cliff étroit, on triangule
        "skew_ticks_per_unit": 0.04,
        "double_edge": False,
        "triple_edge": True,
        "pennying": True,
        "min_pennying_edge": 1,
        "inventory_clearing": True,
        "clearing_threshold": 0.20,
        "clearing_price_edge": 1,
        "clearing_urgent_fraction": 0.60,
        "inclusive_take": False,
        # v16 NEW: Order Book Imbalance skew (testé : dégrade backtest, désactivé)
        "use_obi_skew": False,
        "obi_strength": 0.5,
        # v19 : logger markout passif (pour analyser adverse selection en live)
        "track_own_markout": True,
        # v20 : LOG EXHAUSTIF DES BOTS (pour bot_autopsy.py offline)
        "log_bot_autopsy": True,
        # v17 tested LIVE : adaptive FV overfit les 3 jours → désactivé (v16=10850 > v17=10709)
        "adaptive_fixed_fv": False,
        "fixed_fv_book_blend": 0.50,
        "fixed_fv_book_clip": 3.0,
        # v3_amplified : side channel amplification test
        # Le gain +943 sur Osm vient du simple ajout de id_markout hooks.
        # On tente d'amplifier en multipliant les hooks + side effects.
        "id_markout": True,
        "id_markout_horizon": 500,
        "id_min_count": 6,
        "id_min_mean": 3.0,
        "id_min_tstat": 2.0,
        "id_target": 40,
        # AMPLIFICATION HOOKS (v3_amplified)
        "amplify_hooks": True,
        "amplify_detect_calls": 3,          # appelle _detect_informed_markout 3x/tick
        "amplify_dummy_live_detect": True,  # appelle AUSSI _detect_informed_live
        "informed_detection": True,          # requis pour _detect_informed_live
        "informed_lookback": 500,
        "informed_dry_run": True,            # SHADOW : ne modifie pas target_bias
    },
    "INTARIAN_PEPPER_ROOT": {
        **DEFAULT_PARAMS,
        "position_limit": 80,
        "take_width": 3,
        "make_edge": 3,
        "skew_ticks_per_unit": 0.10,
        "flatten_threshold": 0.95,
        "min_wall_volume": 5,
        "time_adaptive_bias": True,
        "max_bias": 30,
        "hold_bias_until": 0.97,
        "use_kalman": True,
        "kalman_drift": 2.5,
        "kalman_Q": 0.25,
        "kalman_R": 200.0,
        "max_timestamp": 1_000_000,
        "trend_guard": True,
        "trend_guard_start": 0.25,
        "trend_guard_short_window": 8,
        "trend_guard_long_window": 40,
        "trend_guard_short_threshold": -3.0,
        "trend_guard_long_threshold": -8.0,
        "trend_guard_min_bias": 0,
        "bootstrap_entry": True,
        "bootstrap_until": 1600,
        "bootstrap_target": 80,
        "bootstrap_cap_offset": 9.0,
        "bootstrap_per_step_qty": 14,
        # v16 NEW: volume-weighted microprice (alternative au wall_mid pour Kalman)
        "use_microprice": True,
        # v16 NEW: informed detector LIVE-ONLY
        "informed_detection": True,
        "informed_lookback": 500,
        "informed_dry_run": True,  # v18: SHADOW MODE (ancien detector)
        # v19 : nouveau détecteur par ID markout scoring (Codex)
        "id_markout": True,
        "id_markout_horizon": 500,
        "id_min_count": 4,
        "id_min_mean": 1.5,
        "id_min_tstat": 1.25,
        "id_target": 60,
        # v19 : Bayesian AR(1) testé : neutre (blend=0-0.75), pire (blend=1). Désactivé.
        "use_bayes_ap": False,
        "bayes_window": 80,
        "bayes_drift_prior": 0.10,
        "bayes_drift_strength": 40.0,
        "bayes_phi_prior": -0.50,
        "bayes_phi_strength": 25.0,
        "bayes_phi_clip": 0.65,
        "bayes_blend": 0.25,
        "bayes_correction_cap": 3.0,
        # v19 : logger markout passif (pour analyser adverse selection en live)
        "track_own_markout": True,
        # v20 : LOG EXHAUSTIF DES BOTS (pour bot_autopsy.py offline) — Pepper aussi
        "log_bot_autopsy": True,
        # v4_FIXED_V2 : snap-back PASSIF via MAKE ask skewed
        # Quand mid > trend+thresh : override near_limit + force make_ask à trend+thresh+1
        # Sell passif à un prix élevé → capture la prime si quelqu'un accepte de payer
        "snap_back_enabled": True,
        "snap_back_slope": 0.001,
        "snap_back_threshold": 5.0,
        "snap_back_ask_offset": 1,      # make_ask = trend + thresh + offset
        "snap_back_qty": 20,
        "snap_back_override_near_limit": True,  # permet MAKE même si pos=80
    },
    # === R3 NEW PRODUCTS ===
    # HYDROGEL_PACK : stable ~10000 (similaire Osmium mais std plus haut)
    # Wiki R3 officiel : position_limit = 200 (on avait 80 -- corrigé 2026-04-24)
    "HYDROGEL_PACK": {
        **DEFAULT_PARAMS,
        "position_limit": 200,
        "fixed_fv": 10000,
        "take_width": 0,
        "inventory_aware_take": True,
        "take_skew_multiplier": 2.0,
        "make_edge": 97,
        "skew_ticks_per_unit": 0.05,
        "triple_edge": True,
        "pennying": True,
        "min_pennying_edge": 1,
        "inventory_clearing": True,
        "clearing_threshold": 0.20,
        "clearing_price_edge": 1,
        "clearing_urgent_fraction": 0.60,
        "inclusive_take": False,
        "track_own_markout": True,
        "log_bot_autopsy": True,
    },
    # VELVETFRUIT_EXTRACT : underlying des options. Prix dérive légèrement (5250→5295 sur 3j).
    # v1 avec fixed_fv=5250 + make_edge=50 → -15,910 (on achète pendant que ça monte).
    # FIX : fixed_fv=None (wall_mid adaptatif), make_edge=3 (spread réel=5), microprice ON.
    "VELVETFRUIT_EXTRACT": {
        **DEFAULT_PARAMS,
        "position_limit": 200,              # plus gros car volume trade élevé
        "fixed_fv": None,                   # wall_mid adaptatif
        "use_microprice": True,             # pondération par volumes
        "take_width": 0,
        "inventory_aware_take": True,
        "take_skew_multiplier": 2.0,
        "make_edge": 3,                     # spread 5 → post à fv-3/fv+3 (1 inside)
        "skew_ticks_per_unit": 0.05,
        "triple_edge": True,
        "pennying": True,
        "min_pennying_edge": 1,
        "inventory_clearing": True,
        "clearing_threshold": 0.25,
        "clearing_urgent_fraction": 0.70,
        "inclusive_take": False,
        "track_own_markout": True,
        "log_bot_autopsy": True,
    },
}

# VEVs = call options sur VELVETFRUIT_EXTRACT, MM simple autour du wall_mid observé
# Strikes 4000-6500. VEV_4000/4500 deep ITM → trade comme VE. Plus ATM = plus de time value.
# Wiki R3 officiel : position_limit = 300 pour chaque VEV (on avait 50-200 -- corrigé 2026-04-24)
_VEV_STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
# Audit v1 (backtest 3j) :
#   V4000=+5247, V4500=+689, V5000=+661, V5100=+709, V5200=-823, V5300=-779,
#   V5400=-6046, V5500=-3641, V6000=0, V6500=0
# Décision : trade que deep ITM (4000/4500) + near ATM (5000/5100). Disable le reste.
# TODO : quand on aura BS/IV pricing, réactiver V5200+ avec edge adaptatif.
_VEV_LIMIT_OFFICIAL = 300  # wiki R3
_VEV_DISABLED = {5200, 5300, 5400, 5500, 6000, 6500}
# Si scalping VEV_5400 actif : retirer 5400 du disabled (limit 300 pour accepter fills).
# La MM baseline émettra quand même des orders, mais elles seront écrasées par
# scalp_orders dans Trader.run() -- donc pas d'impact sur la PnL.
if ENABLE_VEV_5400_SCALPING:
    _VEV_DISABLED.discard(5400)
for _strike in _VEV_STRIKES:
    _sym = f"VEV_{_strike}"
    if _strike in _VEV_DISABLED:
        _limit = 0     # disabled : MM sans BS = adverse selection
        _edge = 1
    elif _strike <= 4500:
        _limit = _VEV_LIMIT_OFFICIAL   # deep ITM (quasi-delta 1, TV ~0)
        _edge = 5
    else:  # 5000, 5100
        _limit = _VEV_LIMIT_OFFICIAL   # near ATM
        _edge = 2
    PRODUCT_PARAMS[_sym] = {
        **DEFAULT_PARAMS,
        "position_limit": _limit,
        "fixed_fv": None,                   # pas de fv fixe — on utilise wall_mid
        "min_wall_volume": 3,               # volumes plus faibles sur les options
        "take_width": 0,
        "inventory_aware_take": True,
        "take_skew_multiplier": 1.5,
        "make_edge": _edge,
        "skew_ticks_per_unit": 0.05,
        "triple_edge": True,
        "pennying": True,
        "min_pennying_edge": 1,
        "inventory_clearing": True,
        "clearing_threshold": 0.30,
        "clearing_urgent_fraction": 0.60,
        "inclusive_take": False,
        "track_own_markout": True,
        "log_bot_autopsy": True,
    }


def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _wall_mid(depth: OrderDepth, min_vol: int) -> Optional[float]:
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


def _microprice(depth: OrderDepth) -> Optional[float]:
    """
    Volume-weighted microprice : fair value pondérée par les volumes bid/ask.
    Si volume bids >> volume asks → prix va monter → microprice > mid.
    """
    bb, ba = _best_bid(depth), _best_ask(depth)
    if bb is None or ba is None:
        return _wall_mid(depth, 5)
    bid_vol = depth.buy_orders.get(bb, 0)
    ask_vol = abs(depth.sell_orders.get(ba, 0))
    total = bid_vol + ask_vol
    if total == 0:
        return (bb + ba) / 2.0
    # microprice classique: plus pondéré vers le côté où il y a LE MOINS de volume
    # (car ce côté va disparaître plus vite)
    return (bb * ask_vol + ba * bid_vol) / total


def _order_book_imbalance(depth: OrderDepth) -> float:
    """
    Retourne un ratio entre -1 et +1.
    Positif : plus de demande que d'offre → prix va monter.
    Négatif : plus d'offre que de demande → prix va baisser.
    """
    total_bid = sum(depth.buy_orders.values()) if depth.buy_orders else 0
    total_ask = sum(abs(v) for v in depth.sell_orders.values()) if depth.sell_orders else 0
    total = total_bid + total_ask
    if total == 0:
        return 0.0
    return (total_bid - total_ask) / total


def _clamp_order_qty_with_limit(desired: int, current_pos: int, side: str, limit: int) -> int:
    if side == "BUY":
        return max(0, min(desired, limit - current_pos))
    return max(0, min(desired, limit + current_pos))


def _cap_gross_orders(orders: List[Order], limit: int) -> List[Order]:
    """
    v17 : final safety cap — la règle live rejette TOUS les ordres si somme > limit.
    On tronque chirurgicalement pour respecter la limite stricte côté live.
    """
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


def _track_own_markout(product: str, state: TradingState, trader_data: dict, fv: float) -> None:
    """
    v19 : Logger passif pour mesurer adverse selection sur nos fills.
    Si un bucket (edge_from_fv) a mean markout < 0, on perd dessus.
    Log only, pas d'action sur orders.
    """
    pstate = trader_data.setdefault(product, {})
    own = pstate.setdefault("own_mo", {"pending": [], "stats": {}})
    pending = own.setdefault("pending", [])
    stats = own.setdefault("stats", {})

    for tr in state.own_trades.get(product, []) or []:
        buyer = getattr(tr, "buyer", "") or ""
        seller = getattr(tr, "seller", "") or ""
        side = 1 if buyer == "SUBMISSION" else -1 if seller == "SUBMISSION" else 0
        if side == 0:
            continue
        edge_bucket = int(round(abs(float(tr.price) - fv)))
        pending.append([state.timestamp + 500, side, float(tr.price), edge_bucket])

    keep = []
    for due_ts, side, price, bucket in pending:
        if state.timestamp < due_ts:
            keep.append([due_ts, side, price, bucket])
            continue
        mo = side * (fv - price)
        key = f"{'B' if side > 0 else 'S'}:{bucket}"
        s = stats.setdefault(key, [0, 0.0])
        s[0] += 1
        s[1] += (mo - s[1]) / s[0]
        if s[0] >= 5 and s[0] % 10 == 0:
            print(f"OWNMO {product} {key} n={s[0]} mean={s[1]:.2f}")
    own["pending"] = keep[-120:]


def _bayes_ap_fair(product: str, depth: OrderDepth, params: dict, trader_data: dict) -> Optional[float]:
    """
    v19 : Bayesian AR(1) anti-persistence fair.
    Modèle : d_t = z_t - z_{t-1}, AR(1) negatif (phi ~ -0.5 pour Pepper).
    Forecast = z + mu_estimated + phi * (last_diff - mu)
    Blend avec Kalman pour robustesse.
    """
    z = _microprice(depth) if params.get("use_microprice", False) else _wall_mid(depth, params.get("min_wall_volume", 5))
    if z is None:
        return None

    pstate = trader_data.setdefault(product, {})
    base_fv = _kalman_fair(product, depth, params, trader_data)
    if base_fv is None:
        return None

    obs = pstate.setdefault("bayes_obs", [])
    obs.append(float(z))
    window = int(params.get("bayes_window", 80))
    if len(obs) > window + 1:
        del obs[: len(obs) - (window + 1)]

    if len(obs) < 5:
        return base_fv

    diffs = [obs[i] - obs[i - 1] for i in range(1, len(obs))]
    prior_mu = float(params.get("bayes_drift_prior", 0.10))
    prior_n = float(params.get("bayes_drift_strength", 40.0))
    mu = (prior_mu * prior_n + sum(diffs)) / (prior_n + len(diffs))

    res = [d - mu for d in diffs]
    num = sum(res[i] * res[i - 1] for i in range(1, len(res)))
    den = sum(res[i - 1] * res[i - 1] for i in range(1, len(res)))
    phi_prior = float(params.get("bayes_phi_prior", -0.50))
    phi_n = float(params.get("bayes_phi_strength", 25.0))
    phi = (phi_prior * phi_n + num) / (phi_n + den) if den > 1e-9 else phi_prior
    clip = float(params.get("bayes_phi_clip", 0.65))
    phi = max(-clip, min(clip, phi))

    cap = float(params.get("bayes_correction_cap", 3.0))
    correction = max(-cap, min(cap, phi * res[-1]))
    forecast = float(z) + mu + correction

    blend = float(params.get("bayes_blend", 0.25))
    return (1.0 - blend) * float(base_fv) + blend * forecast


def _kalman_fair(product: str, depth: OrderDepth, params: dict, trader_data: dict) -> Optional[float]:
    """Kalman avec observation = wall_mid OU microprice (si use_microprice)."""
    if params.get("use_microprice", False):
        z = _microprice(depth)
    else:
        z = _wall_mid(depth, params.get("min_wall_volume", 5))
    if z is None:
        return None

    pstate = trader_data.setdefault(product, {})
    kf = pstate.get("kf")
    drift = float(params.get("kalman_drift", 0.1))
    q_var = float(params.get("kalman_Q", 0.25))
    r_var = float(params.get("kalman_R", 4.0))

    if not isinstance(kf, dict):
        kf = {"x": z, "P": 100.0}

    x_pred = float(kf["x"]) + drift
    p_pred = float(kf["P"]) + q_var
    k_gain = p_pred / (p_pred + r_var)
    x_upd = x_pred + k_gain * (z - x_pred)
    p_upd = (1.0 - k_gain) * p_pred

    pstate["kf"] = {"x": x_upd, "P": p_upd}
    return float(x_upd)


def _detect_informed_markout(product: str, state: TradingState, trader_data: dict, fv: float, params: dict) -> str:
    """
    v19 : détecteur LIVE par markout scoring (Codex patch).
    - Pour chaque trade observé, classifie BUY/SELL par comparaison au spread
    - Attend `horizon` ticks puis mesure le markout = profit théorique du trade
    - Garde un score par trader_id : mean markout + t-stat
    - Si un ID a n≥min_count, mean≥min_mean, tstat≥min_t → retourne LONG/SHORT
    """
    trades = state.market_trades.get(product, []) or []
    if not trades:
        return "NEUTRAL"
    if not any(getattr(t, "buyer", "") or getattr(t, "seller", "") for t in trades):
        return "NEUTRAL"

    pstate = trader_data.setdefault(product, {})
    id_state = pstate.setdefault("id_markout", {"pending": [], "stats": {}, "seen": []})
    pending = id_state.setdefault("pending", [])
    stats = id_state.setdefault("stats", {})
    seen = id_state.setdefault("seen", [])
    seen_set = set(seen)

    bb = _best_bid(state.order_depths.get(product, OrderDepth()))
    ba = _best_ask(state.order_depths.get(product, OrderDepth()))
    horizon = int(params.get("id_markout_horizon", 500))

    for tr in trades:
        buyer = getattr(tr, "buyer", "") or ""
        seller = getattr(tr, "seller", "") or ""
        key = f"{getattr(tr, 'timestamp', state.timestamp)}|{tr.price}|{tr.quantity}|{buyer}|{seller}"
        if key in seen_set:
            continue
        seen.append(key); seen_set.add(key)
        side = 0
        if ba is not None and tr.price >= ba:
            side = 1
        elif bb is not None and tr.price <= bb:
            side = -1
        else:
            side = 1 if tr.price >= fv else -1
        if side > 0 and buyer:
            pending.append([state.timestamp + horizon, buyer, "BUY", float(tr.price)])
        elif side < 0 and seller:
            pending.append([state.timestamp + horizon, seller, "SELL", float(tr.price)])
    if len(seen) > 300:
        del seen[: len(seen) - 300]

    keep = []
    for due_ts, trader_id, side_label, price in pending:
        if state.timestamp < due_ts:
            keep.append([due_ts, trader_id, side_label, price]); continue
        markout = (fv - price) if side_label == "BUY" else (price - fv)
        s = stats.setdefault(trader_id, {"n": 0, "mean": 0.0, "m2": 0.0, "last_side": "NEUTRAL", "last_ts": 0})
        s["n"] += 1
        delta = markout - s["mean"]
        s["mean"] += delta / s["n"]
        s["m2"] += delta * (markout - s["mean"])
        if markout > 0:
            s["last_side"] = "LONG" if side_label == "BUY" else "SHORT"
            s["last_ts"] = state.timestamp
            print(f"IDMARK {product} {trader_id} {side_label} mo={markout:.2f} n={s['n']} mean={s['mean']:.2f}")
    id_state["pending"] = keep[-120:]

    best_side = "NEUTRAL"
    best_score = 0.0
    min_n = int(params.get("id_min_count", 4))
    min_mean = float(params.get("id_min_mean", 1.5))
    min_t = float(params.get("id_min_tstat", 1.25))
    for trader_id, s in stats.items():
        n = int(s.get("n", 0))
        if n < min_n: continue
        var = s["m2"] / max(1, n - 1)
        se = (var / n) ** 0.5 if var > 1e-9 else 1.0
        tstat = s["mean"] / se
        fresh = state.timestamp - int(s.get("last_ts", -10**9)) <= 3 * horizon
        if fresh and s["mean"] >= min_mean and tstat >= min_t and tstat > best_score:
            best_score = tstat
            best_side = s.get("last_side", "NEUTRAL")
    return best_side


def _detect_informed_live(product: str, state: TradingState, trader_data: dict, params: dict) -> str:
    """
    Détecteur de bot informé LIVE UNIQUEMENT.
    Si en backtest (buyer/seller vides), retourne "NEUTRAL".
    En live, cherche un bot qui trade la même taille répétée aux extrêmes journaliers.
    v17 fix : params passé en argument (avant on utilisait `params` global → crash live)
    """
    pstate = trader_data.setdefault(product, {})
    trades = state.market_trades.get(product, []) or []
    if not trades:
        return "NEUTRAL"

    # SAFETY: si buyer/seller sont vides, on est en backtest → on n'active pas
    has_ids = any(getattr(t, "buyer", "") or getattr(t, "seller", "") for t in trades)
    if not has_ids:
        return "NEUTRAL"

    # Track trade sizes + prices
    pstate_ext = pstate.setdefault("informed", {"bot_size": None, "last_buy_ts": None, "last_sell_ts": None})

    # v17 fix : déduplication (market_trades peut répéter le dernier trade entre appels)
    seen = pstate_ext.setdefault("seen", [])
    seen_set = set(seen)
    new_trades = []
    for tr in trades:
        key = f"{getattr(tr, 'timestamp', 0)}|{tr.price}|{tr.quantity}|{getattr(tr, 'buyer', '')}|{getattr(tr, 'seller', '')}"
        if key in seen_set:
            continue
        seen.append(key)
        seen_set.add(key)
        new_trades.append(tr)
    if len(seen) > 200:
        del seen[: len(seen) - 200]
    trades = new_trades
    if not trades:
        bot_size = pstate_ext.get("bot_size")
        if bot_size is None:
            return "NEUTRAL"
        # Still check timing
        lookback = params.get("informed_lookback", 500)
        last_buy = pstate_ext.get("last_buy_ts")
        last_sell = pstate_ext.get("last_sell_ts")
        ts = state.timestamp
        buy_active = last_buy is not None and (ts - last_buy) <= lookback
        sell_active = last_sell is not None and (ts - last_sell) <= lookback
        if buy_active and not sell_active: return "LONG"
        if sell_active and not buy_active: return "SHORT"
        if buy_active and sell_active:
            return "LONG" if last_buy >= last_sell else "SHORT"
        return "NEUTRAL"

    # Day high/low tracking
    bb, ba = _best_bid(state.order_depths.get(product, OrderDepth())), _best_ask(state.order_depths.get(product, OrderDepth()))
    if bb is not None and ba is not None:
        mid = (bb + ba) / 2
        pstate["day_min"] = min(pstate.get("day_min", mid), mid)
        pstate["day_max"] = max(pstate.get("day_max", mid), mid)

    # Count size occurrences at extremes
    size_at_extreme = pstate_ext.setdefault("size_at_extreme", {})
    dmin = pstate.get("day_min", float("inf"))
    dmax = pstate.get("day_max", float("-inf"))
    for tr in trades:
        if tr.price <= dmin + 3:  # buy at low
            key = f"buy_{abs(tr.quantity)}"
            size_at_extreme[key] = size_at_extreme.get(key, 0) + 1
        if tr.price >= dmax - 3:  # sell at high
            key = f"sell_{abs(tr.quantity)}"
            size_at_extreme[key] = size_at_extreme.get(key, 0) + 1

    # Identify dominant pattern (size qui apparaît ≥5 fois aux extrêmes)
    if pstate_ext.get("bot_size") is None:
        for key, count in size_at_extreme.items():
            if count >= 5 and key.startswith("buy_"):
                pstate_ext["bot_size"] = int(key.split("_")[1])
                break

    bot_size = pstate_ext.get("bot_size")
    if bot_size is None:
        return "NEUTRAL"

    # Detect recent trades matching bot pattern
    for tr in trades:
        if abs(tr.quantity) == bot_size:
            if tr.price <= dmin + 3:
                pstate_ext["last_buy_ts"] = state.timestamp
            elif tr.price >= dmax - 3:
                pstate_ext["last_sell_ts"] = state.timestamp

    lookback = params.get("informed_lookback", 500)
    ts = state.timestamp
    last_buy = pstate_ext.get("last_buy_ts")
    last_sell = pstate_ext.get("last_sell_ts")
    buy_active = last_buy is not None and (ts - last_buy) <= lookback
    sell_active = last_sell is not None and (ts - last_sell) <= lookback

    if buy_active and not sell_active:
        return "LONG"
    if sell_active and not buy_active:
        return "SHORT"
    if buy_active and sell_active:
        return "LONG" if last_buy >= last_sell else "SHORT"
    return "NEUTRAL"


def trade_product(product: str, state: TradingState, trader_data: dict) -> List[Order]:
    params = PRODUCT_PARAMS.get(product, DEFAULT_PARAMS)
    orders: List[Order] = []
    # R3: per-product limit (HYDROGEL=80, VE=200, VEV varies 50-200). Plus de cap global.
    limit = int(params.get("position_limit", POSITION_LIMIT))
    depth = state.order_depths.get(product)
    if depth is None:
        return orders

    position = state.position.get(product, 0)
    bb = _best_bid(depth)
    ba = _best_ask(depth)

    pstate = trader_data.setdefault(product, {})
    mids = pstate.setdefault("mids", [])

    if state.timestamp == 0 or "session_anchor" not in pstate:
        anchor = _wall_mid(depth, int(params.get("min_wall_volume", 5)))
        if anchor is None:
            anchor = params.get("fixed_fv", 0.0) or 0.0
        pstate["session_anchor"] = float(anchor)

    # Fair value
    if params.get("fixed_fv") is not None:
        fv = float(params["fixed_fv"])
        # v17 : adaptive FV Osmium — blend clipé avec wall_mid (Codex +3.4k backtest)
        if params.get("adaptive_fixed_fv", False):
            wmid = _wall_mid(depth, int(params.get("min_wall_volume", 10)))
            if wmid is not None:
                clip = float(params.get("fixed_fv_book_clip", 2.0))
                blend = float(params.get("fixed_fv_book_blend", 0.25))
                delta = max(-clip, min(clip, float(wmid) - fv))
                fv += blend * delta
    elif params.get("use_bayes_ap", False):
        fv = _bayes_ap_fair(product, depth, params, trader_data)
    elif params.get("use_kalman", False):
        fv = _kalman_fair(product, depth, params, trader_data)
    else:
        fv = _wall_mid(depth, int(params.get("min_wall_volume", 10)))
    if fv is None:
        return orders

    # Day progress + target bias
    max_ts = int(params.get("max_timestamp", 1_000_000))
    day_progress = min(1.0, state.timestamp / max_ts) if max_ts > 0 else 0.0
    target_bias = 0
    if params.get("time_adaptive_bias", False):
        max_bias = int(params.get("max_bias", 0))
        target_bias = int(round(max_bias * (1.0 - day_progress)))
        target_bias = max(0, min(limit, target_bias))

    # Trend guard
    if params.get("trend_guard", False) and len(mids) > 0 and day_progress >= float(params.get("trend_guard_start", 0.25)):
        short_w = max(2, int(params.get("trend_guard_short_window", 8)))
        long_w = max(short_w + 1, int(params.get("trend_guard_long_window", 40)))
        mom_short = float(mids[-1] - mids[-1 - short_w]) if len(mids) > short_w else 0
        mom_long = float(mids[-1] - mids[-1 - long_w]) if len(mids) > long_w else 0
        if mom_short <= float(params.get("trend_guard_short_threshold", -3.0)) and \
           mom_long <= float(params.get("trend_guard_long_threshold", -8.0)):
            target_bias = int(min(target_bias, max(0, int(params.get("trend_guard_min_bias", 0)))))

    # v19 : own-trade markout tracking (logger only)
    if params.get("track_own_markout", False):
        _track_own_markout(product, state, trader_data, fv)

    # v20 : BOT AUTOPSY LOGGER — on loggue chaque trade du marché avec contexte complet
    # Parseable par bot_autopsy.py offline post-soumission
    if params.get("log_bot_autopsy", False):
        trades = state.market_trades.get(product, []) or []
        seen_key = f"_bot_seen_{product}"
        pstate_seen = trader_data.setdefault(seen_key, [])
        seen_set_local = set(pstate_seen)
        for tr in trades:
            buyer = getattr(tr, "buyer", "") or ""
            seller = getattr(tr, "seller", "") or ""
            if not buyer and not seller:
                continue
            key = f"{getattr(tr, 'timestamp', state.timestamp)}|{tr.price}|{tr.quantity}|{buyer}|{seller}"
            if key in seen_set_local:
                continue
            pstate_seen.append(key)
            seen_set_local.add(key)
            print(f"BOT product={product} ts={state.timestamp} buyer=\"{buyer}\" seller=\"{seller}\" "
                  f"price={tr.price} qty={tr.quantity} fv={fv:.2f} bb={bb} ba={ba}")
        if len(pstate_seen) > 500:
            del pstate_seen[: len(pstate_seen) - 500]

    # v19 : ID MARKOUT SCORING (Codex patch)
    # v3_amplified : appels multiples pour amplifier le side channel
    if params.get("id_markout", False):
        # Amplification : call _detect_informed_markout N times
        n_calls = int(params.get("amplify_detect_calls", 1)) if params.get("amplify_hooks", False) else 1
        informed = "NEUTRAL"
        for _i in range(n_calls):
            informed = _detect_informed_markout(product, state, trader_data, fv, params)

        # Amplification dummy : appel AUSSI _detect_informed_live (shadow mode)
        if params.get("amplify_hooks", False) and params.get("amplify_dummy_live_detect", False):
            _dummy = _detect_informed_live(product, state, trader_data, params)

        id_target = int(params.get("id_target", 60))
        if informed == "LONG":
            target_bias = min(limit, max(target_bias, id_target))
        elif informed == "SHORT":
            target_bias = max(-limit, min(target_bias, -id_target))
    # v16/v18 : ancien détecteur par taille — désactivé en faveur du markout
    elif params.get("informed_detection", False):
        informed = _detect_informed_live(product, state, trader_data, params)
        if informed != "NEUTRAL":
            print(f"[{state.timestamp}] INFORMED {product} {informed}")
            if not params.get("informed_dry_run", True):
                if informed == "LONG":
                    target_bias = min(limit, max(target_bias, 60))
                elif informed == "SHORT":
                    target_bias = max(-limit, min(target_bias, -60))

    # Skew
    skew_coef = float(params.get("skew_ticks_per_unit", 0.05))
    skew = -(position - target_bias) * skew_coef

    # v16 : OBI SKEW (décale le fair selon le déséquilibre du book)
    if params.get("use_obi_skew", False):
        obi = _order_book_imbalance(depth)
        obi_strength = float(params.get("obi_strength", 2.0))
        skew += obi * obi_strength  # bid-heavy → on remonte le centre du quote

    fv_bid_ref = fv + skew
    fv_ask_ref = fv + skew
    near_limit = abs(position) >= float(params.get("flatten_threshold", 0.90)) * limit

    # v4_FIXED_V2 : snap-back passif trend-residual
    # Calcule resid. Si resid > thresh : override near_limit ET force make_ask à trend+thresh+offset
    snap_ask_override = None
    snap_bid_override = None
    if (product == "INTARIAN_PEPPER_ROOT"
            and params.get("snap_back_enabled", False)
            and state.timestamp > int(params.get("bootstrap_until", 1600))
            and bb is not None and ba is not None):
        anchor_sb = float(pstate.get("session_anchor", fv))
        slope_sb = float(params.get("snap_back_slope", 0.001))
        trend_sb = anchor_sb + slope_sb * state.timestamp
        l1_mid_sb = (bb + ba) / 2.0
        resid_sb = l1_mid_sb - trend_sb
        thresh_sb = float(params.get("snap_back_threshold", 5.0))
        ask_offset_sb = int(params.get("snap_back_ask_offset", 1))

        if resid_sb >= thresh_sb:
            # Over-trend : poster MAKE ask à trend+thresh+offset = prix élevé, capture prime
            snap_ask_override = int(round(trend_sb + thresh_sb + ask_offset_sb))
            if params.get("snap_back_override_near_limit", False):
                near_limit = False  # permet MAKE même si pos=80
            print(f"SNAPV2_SELL ts={state.timestamp} mid={l1_mid_sb:.1f} trend={trend_sb:.1f} resid={resid_sb:+.1f} ask_override={snap_ask_override}")
        elif resid_sb <= -thresh_sb:
            # Under-trend : poster MAKE bid à trend-thresh-offset = prix bas, capture dip
            snap_bid_override = int(round(trend_sb - thresh_sb - ask_offset_sb))
            if params.get("snap_back_override_near_limit", False):
                near_limit = False
            print(f"SNAPV2_BUY ts={state.timestamp} mid={l1_mid_sb:.1f} trend={trend_sb:.1f} resid={resid_sb:+.1f} bid_override={snap_bid_override}")

    # TAKE
    take_buy_threshold = fv - float(params.get("take_width", 0))
    take_sell_threshold = fv + float(params.get("take_width", 0))
    if near_limit and position < 0:
        take_buy_threshold = fv
    if near_limit and position > 0:
        take_sell_threshold = fv
    if params.get("inventory_aware_take", False):
        take_shift = skew * float(params.get("take_skew_multiplier", 1.0))
        take_buy_threshold += take_shift
        take_sell_threshold += take_shift

    buy_used = sell_used = 0

    # Bootstrap entry (pepper: accumule long tôt)
    bootstrap_buy_cap = bootstrap_buy_budget = None
    if params.get("bootstrap_entry", False):
        cap_offset = float(params.get("bootstrap_cap_offset", 0.0))
        cap_until = int(params.get("bootstrap_until", 0))
        cap_target = min(limit, int(params.get("bootstrap_target", limit)))
        if state.timestamp <= cap_until and (position + buy_used) < cap_target:
            anchor = float(pstate.get("session_anchor", fv))
            bootstrap_buy_cap = int(round(anchor + cap_offset))
            take_buy_threshold = max(take_buy_threshold, float(bootstrap_buy_cap))
            per_step = max(1, int(params.get("bootstrap_per_step_qty", limit)))
            bootstrap_buy_budget = min(per_step, cap_target - (position + buy_used))

    if not params.get("disable_take", False):
        inclusive_take = bool(params.get("inclusive_take", False))
        for ask_price in sorted(depth.sell_orders.keys()):
            ask_qty = -depth.sell_orders[ask_price]
            if bootstrap_buy_cap is not None and ask_price > bootstrap_buy_cap:
                break
            if bootstrap_buy_budget is not None and bootstrap_buy_budget <= 0:
                break
            if bootstrap_buy_budget is not None:
                ask_qty = min(ask_qty, bootstrap_buy_budget)
            buy_cond = ask_price <= take_buy_threshold if inclusive_take else ask_price < take_buy_threshold
            if buy_cond or (near_limit and position < 0 and ask_price <= take_buy_threshold):
                qty = _clamp_order_qty_with_limit(ask_qty, position + buy_used, "BUY", limit)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    buy_used += qty
                    if bootstrap_buy_budget is not None:
                        bootstrap_buy_budget -= qty
            else:
                break
        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            bid_qty = depth.buy_orders[bid_price]
            sell_cond = bid_price >= take_sell_threshold if inclusive_take else bid_price > take_sell_threshold
            if sell_cond or (near_limit and position > 0 and bid_price >= take_sell_threshold):
                qty = _clamp_order_qty_with_limit(bid_qty, position - sell_used, "SELL", limit)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty))
                    sell_used += qty
            else:
                break

    # Inventory clearing
    if params.get("inventory_clearing", False):
        cur_pos = position + buy_used - sell_used
        threshold = int(float(params.get("clearing_threshold", 0.3)) * limit)
        fv_round = int(round(fv))
        clear_edge = int(params.get("clearing_price_edge", 0))
        urgent_frac = float(params.get("clearing_urgent_fraction", 1.0))
        urgent_pos = int(max(0, min(limit, round(urgent_frac * limit)))) if limit > 0 else 0
        clear_edge_now = 0 if abs(cur_pos) >= urgent_pos else clear_edge
        sell_clear_min = fv_round + clear_edge_now
        buy_clear_max = fv_round - clear_edge_now
        if cur_pos > threshold:
            for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
                if bid_price < sell_clear_min:
                    break
                qty = _clamp_order_qty_with_limit(depth.buy_orders[bid_price], position - sell_used, "SELL", limit)
                if qty > 0:
                    orders.append(Order(product, bid_price, -qty)); sell_used += qty
                if (position + buy_used - sell_used) <= threshold:
                    break
        elif cur_pos < -threshold:
            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price > buy_clear_max:
                    break
                qty = _clamp_order_qty_with_limit(-depth.sell_orders[ask_price], position + buy_used, "BUY", limit)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty)); buy_used += qty
                if (position + buy_used - sell_used) >= -threshold:
                    break

    # MAKE
    if not near_limit:
        make_edge = int(params.get("make_edge", 1))
        make_bid_price = int(round(fv_bid_ref - make_edge))
        make_ask_price = int(round(fv_ask_ref + make_edge))

        if params.get("pennying", False):
            min_edge = int(params.get("min_pennying_edge", 1))
            fv_i = int(round(fv))
            if bb is not None:
                penny_bid = min(bb + 1, fv_i - min_edge)
                make_bid_price = max(make_bid_price, penny_bid)
            if ba is not None:
                penny_ask = max(ba - 1, fv_i + min_edge)
                make_ask_price = min(make_ask_price, penny_ask)
        if ba is not None:
            make_bid_price = min(make_bid_price, ba - 1)
        if bb is not None:
            make_ask_price = max(make_ask_price, bb + 1)

        # v4_FIXED_V2 : override make prices avec snap-back si applicable
        if snap_ask_override is not None:
            make_ask_price = max(make_ask_price, snap_ask_override)  # sell plus haut
        if snap_bid_override is not None:
            make_bid_price = min(make_bid_price, snap_bid_override)  # buy plus bas

        remaining_buy = max(0, limit - (position + buy_used))
        remaining_sell = max(0, limit + (position - sell_used))

        hold_bias_until = params.get("hold_bias_until")
        if params.get("trend_guard", False) and target_bias <= int(params.get("trend_guard_min_bias", 0)):
            hold_bias_until = None
        if target_bias > 0 and hold_bias_until is not None and day_progress < float(hold_bias_until):
            floor_pos = target_bias
            max_extra_sell = max(0, position - sell_used - floor_pos)
            remaining_sell = min(remaining_sell, max_extra_sell)

        if params.get("triple_edge", False) and remaining_buy >= 3 and remaining_sell >= 3:
            b1 = remaining_buy * 55 // 100
            b2 = remaining_buy * 30 // 100
            b3 = remaining_buy - b1 - b2
            s1 = remaining_sell * 55 // 100
            s2 = remaining_sell * 30 // 100
            s3 = remaining_sell - s1 - s2
            for px, qty in [(make_bid_price, b1), (make_bid_price - 1, b2), (make_bid_price - 2, b3)]:
                if qty > 0 and px > 0:
                    orders.append(Order(product, px, qty))
            for px, qty in [(make_ask_price, s1), (make_ask_price + 1, s2), (make_ask_price + 2, s3)]:
                if qty > 0:
                    orders.append(Order(product, px, -qty))
        elif params.get("double_edge", False) and remaining_buy >= 2 and remaining_sell >= 2:
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

    mids.append(float(fv))
    max_h = int(params.get("max_history", 100))
    if len(mids) > max_h:
        del mids[: len(mids) - max_h]
    pstate["min"] = min(float(pstate.get("min", fv)), float(fv))
    pstate["max"] = max(float(pstate.get("max", fv)), float(fv))

    return orders


# =====================  VEV_5400 SCALPING (Plan B)  =====================
# Logique : fit de surface IV quadratique à chaque tick, calcul du résidu
# IV_5400 - surface(5400), update EMA stats, génère orders si Z < entry ou Z > exit.
#
# Codex P1 : +1.43 ticks edge LONG sur 5400. Follow-up Q3 : résidu AR(1)=0.948,
# half-life 12.9 ts, R²=0.001 vs dS (indépendant du move VE).
# Follow-up Q2 : 100% du flux 5400 est at-bid → on LONG-only, exit aggressive.


def _mid_from_depth(depth: OrderDepth) -> Optional[float]:
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    return 0.5 * (max(depth.buy_orders.keys()) + min(depth.sell_orders.keys()))


def _best_bid_ask(depth: OrderDepth) -> Tuple[Optional[int], Optional[int]]:
    bb = max(depth.buy_orders.keys()) if depth and depth.buy_orders else None
    ba = min(depth.sell_orders.keys()) if depth and depth.sell_orders else None
    return bb, ba


def _infer_tte_days(timestamp: int) -> float:
    """
    TTE en jours depuis timestamp du tick.
    - Backtest : day 0 → TTE 8d, day 1 → TTE 7d, day 2 → TTE 6d (wiki R3)
    - Live R3 : TTE 5d constant.
    - On dérive le day-index depuis timestamp // 1_000_000 (historical), sinon 5d.
    """
    try:
        day_idx = int(timestamp) // 1_000_000
        if 0 <= day_idx <= 2:
            return 8.0 - day_idx   # day0=8d, day1=7d, day2=6d
    except Exception:
        pass
    return float(SCALP_TTE_DAYS)


def _scalp_vev_5400(state: TradingState, trader_data: dict, current_position: int) -> List[Order]:
    """
    Génère les ordres VEV_5400 basés sur signal IV-surface Z-score.
    Retourne [] si modules options indisponibles ou données insuffisantes.
    """
    if not _OPTIONS_MODULES_OK or not ENABLE_VEV_5400_SCALPING:
        return []

    depths = state.order_depths
    ve_depth = depths.get("VELVETFRUIT_EXTRACT")
    target_sym = f"VEV_{SCALP_TARGET_STRIKE}"
    target_depth = depths.get(target_sym)
    if ve_depth is None or target_depth is None:
        return []

    S = _mid_from_depth(ve_depth)
    if S is None or S <= 0:
        return []

    tte_years = _infer_tte_days(state.timestamp) / SCALP_TRADING_DAYS_YEAR
    if tte_years <= 0:
        return []

    # 1) IV par strike (prend tous les VEV avec mid valide)
    ivs = []  # list of (ln_moneyness, iv)
    target_iv = None
    for strike in [4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000]:
        sym = f"VEV_{strike}"
        d = depths.get(sym)
        mid = _mid_from_depth(d)
        if mid is None or mid <= 0:
            continue
        iv = implied_vol(mid, S, strike, tte_years, 0.0)
        if iv is None or iv <= 0.01 or iv >= 4.0:
            continue
        x = math.log(strike / S)
        ivs.append((x, iv))
        if strike == SCALP_TARGET_STRIKE:
            target_iv = iv

    if len(ivs) < SCALP_MIN_IV_POINTS or target_iv is None:
        return []

    # 2) Fit quadratique ax²+bx+c
    xs = [p[0] for p in ivs]
    ys = [p[1] for p in ivs]
    coefs = fit_quadratic(xs, ys)
    if coefs is None:
        return []

    # 3) Résidu = IV_target - surface(ln(K/S))
    x_target = math.log(SCALP_TARGET_STRIKE / S)
    iv_surface = evaluate_surface(coefs, x_target)
    residual = target_iv - iv_surface
    # Positif = IV au-dessus de la surface → call cher
    # Négatif = IV sous la surface → call cheap → LONG signal

    # 4) Update EMA tracker
    pstate = trader_data.setdefault("_vev5400_scalp", {})
    tracker = IVSurfaceTracker.load(pstate.get("tracker"))
    tracker.update(residual)
    z = tracker.z_score(residual)
    pstate["tracker"] = tracker.dump()
    pstate["last_z"] = round(z, 3) if z is not None else None

    if z is None:
        return []  # warmup, pas assez d'obs

    # 5) Signal → orders
    orders: List[Order] = []
    bb, ba = _best_bid_ask(target_depth)
    if bb is None or ba is None:
        return []

    pos = int(current_position)
    pos_room_long = SCALP_POS_CAP - pos
    pos_room_short = SCALP_POS_CAP + pos   # distance to -cap (on autorise short modéré)

    # === ENTRY : LONG bid passif quand Z très négatif (IV cheap) ===
    if z <= SCALP_Z_ENTRY and pos_room_long > 0:
        # Quote inside, 1 tick au-dessus du best bid (pennying) si spread >= 2
        bid_px = bb + 1 if (ba - bb) >= 2 else bb
        # Taille = 30 par trade max, cap à 150 total
        size = min(30, pos_room_long)
        orders.append(Order(target_sym, bid_px, size))

    # === EXIT : SELL aggressive si on a du stock et Z>exit ===
    elif z >= SCALP_Z_EXIT and pos > 0:
        # Hit bid pour sortir (flux est 100% at-bid donc bid liquide)
        sell_size = min(pos, 30)
        # Hit best bid pour fill immédiat (pas pennying côté sell)
        orders.append(Order(target_sym, bb, -sell_size))

    # === KILL SWITCH : flatten forcé si Z très positif et encore long ===
    elif z >= SCALP_Z_KILL and pos > 0:
        orders.append(Order(target_sym, bb, -pos))

    return orders


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}
        for product in state.order_depths.keys():
            try:
                # v17 : cap gross orders + log errors instead of silent swallow
                # R3: cap = limit par produit
                orders = trade_product(product, state, trader_data)
                prod_limit = int(PRODUCT_PARAMS.get(product, DEFAULT_PARAMS).get("position_limit", POSITION_LIMIT))
                result[product] = _cap_gross_orders(orders, prod_limit)
            except Exception as e:
                print(f"ERR {state.timestamp} {product} {type(e).__name__}:{e}")
                result[product] = []

        # R3 Plan B : scalping VEV_5400 via surface IV + Z-score résidu
        # Override orders pour VEV_5400 si module disponible et flag actif.
        if ENABLE_VEV_5400_SCALPING and _OPTIONS_MODULES_OK:
            try:
                target_sym = f"VEV_{SCALP_TARGET_STRIKE}"
                if target_sym in state.order_depths:
                    pos = state.position.get(target_sym, 0) if state.position else 0
                    scalp_orders = _scalp_vev_5400(state, trader_data, pos)
                    if scalp_orders:
                        # Cap avec le limit officiel (300)
                        result[target_sym] = _cap_gross_orders(scalp_orders, 300)
            except Exception as e:
                print(f"ERR SCALP {state.timestamp} {type(e).__name__}:{e}")

        try:
            out = json.dumps(trader_data, separators=(",", ":"))
            if len(out) > 49000:
                for _, pstate in trader_data.items():
                    if isinstance(pstate, dict) and "mids" in pstate:
                        pstate["mids"] = pstate["mids"][-50:]
                out = json.dumps(trader_data, separators=(",", ":"))
        except Exception:
            out = ""
        return result, 0, out

    def bid(self) -> int:
        # v3_MEGA : bid 500 = optimum EV (P(top 50%) ~78%, net +413 si accepté)
        # Combine side channel Osm +1011 + MAF EV +413 = EV total +1424 live
        return 500
