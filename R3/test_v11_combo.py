"""
v11 = v9 (HYD regime) + seuils optimisés (10015/9945) + limit=300.
Test gain combiné sur jour 2 0-100k.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate
from datamodel import Order

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}

import trader_r3
_RAW_TRADE = trader_r3.trade_product


def make_patched_trade(short_thresh, long_thresh, mom_window, size, limit):
    def patched(product, state, trader_data):
        params = trader_r3.PRODUCT_PARAMS.get(product, trader_r3.DEFAULT_PARAMS)
        if params.get("hyd_regime", False) and product == "HYDROGEL_PACK":
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                return _RAW_TRADE(product, state, trader_data)
            bb = max(depth.buy_orders.keys())
            ba = min(depth.sell_orders.keys())
            mid_now = (bb + ba) / 2.0
            position = state.position.get(product, 0)

            pstate = trader_data.setdefault(product, {})
            mids = pstate.setdefault("mids", [])
            mids.append(float(mid_now))
            if len(mids) > 50:
                del mids[: len(mids) - 50]
            mom = (mids[-1] - mids[-1 - mom_window]) if len(mids) > mom_window else 0.0

            orders = []
            if mid_now >= short_thresh:
                sell_room = limit + position
                qty_sell = min(sell_room, size, depth.buy_orders.get(bb, 0))
                if qty_sell > 0:
                    orders.append(Order(product, bb, -qty_sell))
                ask_px = max(bb + 1, ba - 1)
                extra_sell = sell_room - qty_sell
                if extra_sell > 0:
                    orders.append(Order(product, ask_px, -min(extra_sell, size)))
            elif mid_now < long_thresh and mom > 0:
                buy_room = limit - position
                qty_buy = min(buy_room, size, -depth.sell_orders.get(ba, 0))
                if qty_buy > 0:
                    orders.append(Order(product, ba, qty_buy))
                bid_px = min(ba - 1, bb + 1)
                extra_buy = buy_room - qty_buy
                if extra_buy > 0:
                    orders.append(Order(product, bid_px, min(extra_buy, size)))
            elif mid_now < long_thresh:
                buy_room = limit - position
                if buy_room > 0 and position < size:
                    orders.append(Order(product, bb, min(buy_room, size // 2)))
            elif mid_now > 9970 and mid_now < short_thresh and mom < 0:
                if position > 0:
                    orders.append(Order(product, bb, -min(position, size)))
            else:
                edge = 3
                mid_i = int(round(mid_now))
                buy_room = limit - position; sell_room = limit + position
                if buy_room > 0:
                    orders.append(Order(product, mid_i - edge, min(buy_room, size)))
                if sell_room > 0:
                    orders.append(Order(product, mid_i + edge, -min(sell_room, size)))
            return orders
        return _RAW_TRADE(product, state, trader_data)
    return patched


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


def run_jour2(short_thresh=10010, long_thresh=9950, mom_window=5, size=50, limit=200):
    reset()
    PP["HYDROGEL_PACK"]["position_limit"] = limit
    trader_r3.trade_product = make_patched_trade(short_thresh, long_thresh, mom_window, size, limit)
    try:
        pnl = simulate(2, max_ts=100_000)
        return sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0)
    finally:
        trader_r3.trade_product = _RAW_TRADE


def run_3d(short_thresh=10010, long_thresh=9950, mom_window=5, size=50, limit=200):
    reset()
    PP["HYDROGEL_PACK"]["position_limit"] = limit
    trader_r3.trade_product = make_patched_trade(short_thresh, long_thresh, mom_window, size, limit)
    try:
        total = 0; hyd = 0
        for d in (0, 1, 2):
            pnl = simulate(d)
            total += sum(pnl.values())
            hyd += pnl.get("HYDROGEL_PACK", 0)
        return total, hyd
    finally:
        trader_r3.trade_product = _RAW_TRADE


print("=" * 100, flush=True)
print("v11 COMBO — seuils optimaux 10015/9945 + limit boosté", flush=True)
print("=" * 100, flush=True)

# v9 baseline
t, h = run_jour2(10010, 9950, 5, 50, 200)
print(f"v9 baseline (10010/9950/mw5/sz50/lim200)    jour2={t:+.0f}  HYD={h:+.0f}", flush=True)

# Best seuils only (sans limit boost)
t, h = run_jour2(10015, 9945, 5, 50, 200)
print(f"v9 + best seuils (10015/9945/mw5/lim200)    jour2={t:+.0f}  HYD={h:+.0f}", flush=True)

print(flush=True)
print("--- Sweep limit avec best seuils ---", flush=True)
for lim in [200, 220, 250, 280, 300, 350, 400]:
    t, h = run_jour2(10015, 9945, 5, 50, lim)
    print(f"  seuils 10015/9945 limit={lim:>3d}            jour2={t:+.0f}  HYD={h:+.0f}", flush=True)

print(flush=True)
print("--- Sweep size avec best seuils + lim 300 ---", flush=True)
for sz in [30, 50, 80, 100, 150, 200]:
    t, h = run_jour2(10015, 9945, 5, sz, 300)
    print(f"  seuils 10015/9945 sz={sz:>3d} lim=300        jour2={t:+.0f}  HYD={h:+.0f}", flush=True)

print(flush=True)
print("--- 3j × 1M régression best v11 ---", flush=True)
t3, h3 = run_3d(10015, 9945, 5, 50, 300)
print(f"v11 (10015/9945/mw5/sz50/lim300)           3d={t3:+.0f}  HYD 3d={h3:+.0f}", flush=True)
t3v9, h3v9 = run_3d(10010, 9950, 5, 50, 200)
print(f"v9 baseline (10010/9950/mw5/sz50/lim200)   3d={t3v9:+.0f}  HYD 3d={h3v9:+.0f}", flush=True)
