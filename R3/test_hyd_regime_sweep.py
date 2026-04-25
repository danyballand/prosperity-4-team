"""
HYD regime — grille fine seuils.
v9 actuel : SHORT >=10010, LONG_CAP <9950+mom>0, AVOID 9970-10010+mom<0.
Tester variantes seuils + momentum window.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


# Note : on doit modifier les seuils dans le code, pas via params (hardcodés actuellement).
# Approche pragmatique : monkey-patch trade_product temporairement avec seuils variables.
# OU : faire un nouveau patch hyd_regime_v2 paramétré. Plus simple : ajouter params optionnels.

# Modifions trader_r3.py pour accepter les seuils en params :

import trader_r3
_RAW_TRADE = trader_r3.trade_product


def make_trade_product(short_thresh, long_thresh, mom_window, size):
    """Wrapper qui ajuste les seuils HYD regime."""
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
            limit = int(params.get("position_limit", 200))

            pstate = trader_data.setdefault(product, {})
            mids = pstate.setdefault("mids", [])
            mids.append(float(mid_now))
            if len(mids) > 50:
                del mids[: len(mids) - 50]
            mom = (mids[-1] - mids[-1 - mom_window]) if len(mids) > mom_window else 0.0

            from datamodel import Order
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


def run_jour2(short_thresh, long_thresh, mom_window, size):
    reset()
    trader_r3.trade_product = make_trade_product(short_thresh, long_thresh, mom_window, size)
    try:
        pnl = simulate(2, max_ts=100_000)
        return sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0)
    finally:
        trader_r3.trade_product = _RAW_TRADE


print("=" * 100, flush=True)
print("HYD REGIME SWEEP — short_thresh × long_thresh × mom_window × size", flush=True)
print("=" * 100, flush=True)

# v9 baseline
t_base, h_base = run_jour2(10010, 9950, 5, 50)
print(f"v9 baseline (10010/9950/mom5/sz50) : TOTAL={t_base:+.0f}  HYD={h_base:+.0f}", flush=True)
print(flush=True)

print(f"{'config':<40s}  {'TOTAL':>8s}  {'HYD':>8s}  {'Δ':>8s}", flush=True)
print("-" * 100, flush=True)

best = None
best_t = t_base
configs = []
for st in [10005, 10008, 10010, 10012, 10015]:
    for lt in [9945, 9948, 9950, 9955, 9960]:
        for mw in [3, 5, 8, 10]:
            for sz in [50, 100]:
                configs.append((st, lt, mw, sz))

for st, lt, mw, sz in configs:
    t, h = run_jour2(st, lt, mw, sz)
    delta = t - t_base
    flag = ""
    if t > best_t + 200:
        best_t = t; best = (st, lt, mw, sz, t, h); flag = " ★"
    print(f"st={st} lt={lt} mw={mw:<2d} sz={sz:<3d}  {t:>+8.0f}  {h:>+8.0f}  {delta:>+8.0f}{flag}", flush=True)

print(flush=True)
if best:
    st, lt, mw, sz, t, h = best
    print(f"BEST : st={st} lt={lt} mw={mw} sz={sz} → jour2_100k = {t:+.0f}  (Δ={t-t_base:+.0f})", flush=True)
else:
    print("Aucun config bat v9 de plus de 200", flush=True)
