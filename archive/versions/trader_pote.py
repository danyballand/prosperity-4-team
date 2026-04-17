import json
from typing import Dict, List, Optional, Tuple

from datamodel import Order, OrderDepth, TradingState


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
        "make_edge": 20,
        "skew_ticks_per_unit": 0.04,
        "extra_skew_factor": 0.0,
        "double_edge": False,
        "triple_edge": True,
        "pennying": True,
        "min_pennying_edge": 1,
        "inventory_clearing": True,
        "clearing_threshold": 0.20,
        "clearing_price_edge": 1,
        "clearing_urgent_fraction": 0.60,
        "inclusive_take": False,
        "adaptive_fixed_fv": False,
        "fixed_fv_book_blend": 0.30,
        "fixed_fv_book_clip": 3.0,
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
    },
}


def _best_bid(depth: OrderDepth) -> Optional[int]:
    return max(depth.buy_orders.keys()) if depth.buy_orders else None


def _best_ask(depth: OrderDepth) -> Optional[int]:
    return min(depth.sell_orders.keys()) if depth.sell_orders else None


def _wall_mid(depth: OrderDepth, min_vol: int) -> Optional[float]:
    bid_wall = None
    ask_wall = None

    if depth.buy_orders:
        bid_wall = max(
            (p for p, q in depth.buy_orders.items() if q >= min_vol),
            key=lambda p: depth.buy_orders[p],
            default=None,
        )
    if depth.sell_orders:
        ask_wall = min(
            (p for p, q in depth.sell_orders.items() if -q >= min_vol),
            key=lambda p: depth.sell_orders[p],
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


def _clamp_order_qty_with_limit(desired: int, current_pos: int, side: str, limit: int) -> int:
    if side == "BUY":
        room = limit - current_pos
        return max(0, min(desired, room))
    room = limit + current_pos
    return max(0, min(desired, room))


def _kalman_fair(product: str, depth: OrderDepth, params: dict, trader_data: dict) -> Optional[float]:
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


def trade_product(product: str, state: TradingState, trader_data: dict) -> List[Order]:
    params = PRODUCT_PARAMS.get(product, DEFAULT_PARAMS)
    orders: List[Order] = []

    limit = min(POSITION_LIMIT, int(params.get("position_limit", POSITION_LIMIT)))
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

    if params.get("fixed_fv") is not None:
        fv = float(params["fixed_fv"])
        if params.get("adaptive_fixed_fv", False):
            wmid = _wall_mid(depth, int(params.get("min_wall_volume", 10)))
            if wmid is not None:
                clip = float(params.get("fixed_fv_book_clip", 2.0))
                blend = float(params.get("fixed_fv_book_blend", 0.25))
                delta = max(-clip, min(clip, float(wmid) - fv))
                fv += blend * delta
    elif params.get("use_kalman", False):
        fv = _kalman_fair(product, depth, params, trader_data)
    else:
        fv = _wall_mid(depth, int(params.get("min_wall_volume", 10)))
    if fv is None:
        return orders

    max_ts = int(params.get("max_timestamp", 1_000_000))
    day_progress = min(1.0, state.timestamp / max_ts) if max_ts > 0 else 0.0
    target_bias = 0
    if params.get("time_adaptive_bias", False):
        max_bias = int(params.get("max_bias", 0))
        target_bias = int(round(max_bias * (1.0 - day_progress)))
        target_bias = max(0, min(limit, target_bias))

    if params.get("trend_guard", False) and len(mids) > 0 and day_progress >= float(params.get("trend_guard_start", 0.25)):
        short_w = max(2, int(params.get("trend_guard_short_window", 8)))
        long_w = max(short_w + 1, int(params.get("trend_guard_long_window", 40)))
        mom_short = 0.0
        mom_long = 0.0
        if len(mids) > short_w:
            mom_short = float(mids[-1] - mids[-1 - short_w])
        if len(mids) > long_w:
            mom_long = float(mids[-1] - mids[-1 - long_w])
        if mom_short <= float(params.get("trend_guard_short_threshold", -3.0)) and mom_long <= float(
            params.get("trend_guard_long_threshold", -8.0)
        ):
            target_bias = int(min(target_bias, max(0, int(params.get("trend_guard_min_bias", 0)))))

    skew_coef = float(params.get("skew_ticks_per_unit", 0.05))
    extra_skew = float(params.get("extra_skew_factor", 0.0))
    if extra_skew > 0.0 and limit > 0:
        load = abs(position - target_bias) / float(limit)
        skew_coef *= 1.0 + extra_skew * max(0.0, load - 0.5)

    skew = -(position - target_bias) * skew_coef
    fv_bid_ref = fv + skew
    fv_ask_ref = fv + skew

    near_limit = abs(position) >= float(params.get("flatten_threshold", 0.90)) * limit

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

    buy_used = 0
    sell_used = 0

    bootstrap_buy_cap: Optional[int] = None
    bootstrap_buy_budget: Optional[int] = None
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
                    orders.append(Order(product, bid_price, -qty))
                    sell_used += qty
                if (position + buy_used - sell_used) <= threshold:
                    break
        elif cur_pos < -threshold:
            for ask_price in sorted(depth.sell_orders.keys()):
                if ask_price > buy_clear_max:
                    break
                qty = _clamp_order_qty_with_limit(-depth.sell_orders[ask_price], position + buy_used, "BUY", limit)
                if qty > 0:
                    orders.append(Order(product, ask_price, qty))
                    buy_used += qty
                if (position + buy_used - sell_used) >= -threshold:
                    break

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

            bid_levels = [
                (make_bid_price, b1),
                (make_bid_price - 1, b2),
                (make_bid_price - 2, b3),
            ]
            ask_levels = [
                (make_ask_price, s1),
                (make_ask_price + 1, s2),
                (make_ask_price + 2, s3),
            ]
            for px, qty in bid_levels:
                if qty > 0 and px > 0:
                    orders.append(Order(product, px, qty))
            for px, qty in ask_levels:
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


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            trader_data = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            trader_data = {}

        result: Dict[str, List[Order]] = {}
        for product in state.order_depths.keys():
            try:
                result[product] = trade_product(product, state, trader_data)
            except Exception:
                result[product] = []

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