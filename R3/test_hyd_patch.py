"""
Test patch HYD défensif :
  v6 baseline       : clip=50, take_width=2
  v6_hyd_patch_a    : clip=40, take_width=3
  v6_hyd_patch_b    : clip=30, take_width=3
  v6_hyd_patch_c    : clip=40, take_width=3, trend_guard activé

Objectif : réduire worst rolling W=100k de -14k à <-10k SANS tuer PnL total.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from collections import defaultdict
import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import (Trader, OrderDepth, Order, Listing, TradingState,
                                load_prices, load_trades, apply_passive_fills,
                                fill_crossing, _limit_for, PRODUCTS)

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}


def reset():
    PP.clear()
    for k, v in BASE_PP.items():
        PP[k] = dict(v)


def apply_patch(variant):
    reset()
    if variant == "v6":
        return
    if variant == "patch_a":
        PP["HYDROGEL_PACK"]["fixed_fv_book_clip"] = 40.0
        PP["HYDROGEL_PACK"]["take_width"] = 3
    elif variant == "patch_b":
        PP["HYDROGEL_PACK"]["fixed_fv_book_clip"] = 30.0
        PP["HYDROGEL_PACK"]["take_width"] = 3
    elif variant == "patch_c":
        PP["HYDROGEL_PACK"]["fixed_fv_book_clip"] = 40.0
        PP["HYDROGEL_PACK"]["take_width"] = 3
        PP["HYDROGEL_PACK"]["trend_guard"] = True
        PP["HYDROGEL_PACK"]["trend_guard_start"] = 0.10
        PP["HYDROGEL_PACK"]["trend_guard_short_window"] = 8
        PP["HYDROGEL_PACK"]["trend_guard_long_window"] = 40
        PP["HYDROGEL_PACK"]["trend_guard_short_threshold"] = -3.0
        PP["HYDROGEL_PACK"]["trend_guard_long_threshold"] = -8.0
        PP["HYDROGEL_PACK"]["trend_guard_min_bias"] = 0


def simulate_curve(day, max_ts=1_000_000):
    snapshots = load_prices(day, max_ts)
    trades_by_ts = load_trades(day, max_ts)
    trader = Trader()
    positions = defaultdict(int)
    cash = defaultdict(float)
    trader_data = ""
    listings = {p: Listing(p, p, "SEASHELLS") for p in PRODUCTS}
    timestamps = sorted(snapshots.keys())
    pending_passive = {p: [] for p in PRODUCTS}
    pending_depth = {p: None for p in PRODUCTS}
    prev_market_trades = {p: [] for p in PRODUCTS}
    pnl_curve = []
    by_prod_curve = {p: [] for p in PRODUCTS}
    ts_curve = []
    for ts in timestamps:
        depths = snapshots[ts]
        for p in PRODUCTS:
            if pending_passive[p]:
                trades_now = trades_by_ts.get(ts, {}).get(p, [])
                apply_passive_fills(pending_passive[p], trades_now, pending_depth[p],
                                    positions, cash, p, _limit_for(p))
        pending_passive = {p: [] for p in PRODUCTS}
        state = TradingState(
            traderData=trader_data, timestamp=ts, listings=listings,
            order_depths=depths, own_trades={p: [] for p in PRODUCTS},
            market_trades=prev_market_trades, position=dict(positions), observations=None,
        )
        try:
            result, _, trader_data = trader.run(state)
        except Exception:
            prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue
        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None: continue
            limit = _limit_for(product)
            dm = OrderDepth(); dm.buy_orders = dict(depth.buy_orders); dm.sell_orders = dict(depth.sell_orders)
            passive_orders_this_product = []
            for order in orders:
                remaining = fill_crossing(order, dm, positions, cash, product, limit)
                if remaining != 0:
                    passive_orders_this_product.append(Order(order.symbol, order.price, remaining))
            pending_passive[product] = passive_orders_this_product
            pending_depth[product] = dm
        prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
        total = 0.0
        for p in PRODUCTS:
            depth = depths.get(p)
            if depth and depth.buy_orders and depth.sell_orders:
                mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
            elif depth and depth.buy_orders: mid = max(depth.buy_orders)
            elif depth and depth.sell_orders: mid = min(depth.sell_orders)
            else: mid = 0.0
            pp = cash[p] + positions[p] * mid
            by_prod_curve[p].append(pp)
            total += pp
        pnl_curve.append(total)
        ts_curve.append(ts)
    return ts_curve, pnl_curve, by_prod_curve


def rolling_worst(curve, ts_curve, window_ts):
    n = len(ts_curve)
    if n < 2: return 0.0
    worst = 0.0
    j = 0
    for i in range(n):
        while j < n and ts_curve[j] - ts_curve[i] < window_ts: j += 1
        if j > i + 1:
            end = j - 1 if j - 1 > i else i + 1
            if end >= n: continue
            delta = curve[end] - curve[i]
            if delta < worst: worst = delta
    return worst


variants = ["v6", "patch_a", "patch_b", "patch_c"]
windows = [25_000, 50_000, 100_000]

print("=" * 100, flush=True)
print("HYD PATCH TEST — clip + take_width + trend_guard", flush=True)
print("=" * 100, flush=True)
print(f"{'Variant':<10s}  {'Total 3d':>10s}  W=25k worst3   W=50k worst3   W=100k worst3", flush=True)
print("-" * 100, flush=True)

for v in variants:
    apply_patch(v)
    totals = []
    worsts_by_w = {w: [] for w in windows}
    for d in (0, 1, 2):
        ts_curve, pnl_curve, _ = simulate_curve(d)
        totals.append(pnl_curve[-1] if pnl_curve else 0)
        for w in windows:
            worsts_by_w[w].append(rolling_worst(pnl_curve, ts_curve, w))
    total_3d = sum(totals)
    line = f"{v:<10s}  {total_3d:>+10.0f}  "
    for w in windows:
        worst3 = min(worsts_by_w[w])
        line += f"  W={w//1000}k:{worst3:>+8.0f}"
    print(line, flush=True)

print("-" * 100, flush=True)
print(flush=True)
print("DÉCISION :", flush=True)
print("  PnL total ≥ +145k ET worst W=100k > -10k → patch validé, submit", flush=True)
print("  PnL total < +140k → patch tue trop le PnL, garder v6", flush=True)
print("  Worst W=100k toujours < -12k → patch insuffisant, garder v6", flush=True)
