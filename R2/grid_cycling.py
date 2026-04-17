"""
Grid search Pepper cycling params.
"""
import sys
import os
import copy
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
R1_DIR = os.path.abspath(os.path.join(HERE, "..", "R1"))
sys.path.insert(0, HERE)
sys.path.insert(0, R1_DIR)

from datamodel import OrderDepth, TradingState, Order, Listing, Trade
import trader_r2_v2 as trader_module

import csv
DATA_DIR = os.path.join(HERE, "data")
DAYS = [-1, 0, 1]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]
LIVE_DURATION_TS = 100_000


def load_prices(day):
    path = os.path.join(DATA_DIR, f"prices_round_2_day_{day}.csv")
    snapshots = defaultdict(dict)
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if ts >= LIVE_DURATION_TS: continue
            p = row["product"]; od = OrderDepth()
            for i in (1, 2, 3):
                bp = row.get(f"bid_price_{i}", ""); bv = row.get(f"bid_volume_{i}", "")
                ap = row.get(f"ask_price_{i}", ""); av = row.get(f"ask_volume_{i}", "")
                if bp and bv: od.buy_orders[int(bp)] = int(bv)
                if ap and av: od.sell_orders[int(ap)] = -int(av)
            snapshots[ts][p] = od
    return snapshots


def load_trades(day):
    path = os.path.join(DATA_DIR, f"trades_round_2_day_{day}.csv")
    trades_by_ts = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if ts >= LIVE_DURATION_TS: continue
            prod = row["symbol"]
            price = int(float(row["price"]))
            qty = int(row["quantity"])
            trades_by_ts[ts][prod].append(Trade(symbol=prod, price=price, quantity=qty,
                                                buyer="", seller="", timestamp=ts))
    return trades_by_ts


def fill_crossing(order, depth, positions, cash, product, limit):
    if order.quantity > 0:
        for ask_p in sorted(list(depth.sell_orders.keys())):
            if order.price < ask_p or order.quantity <= 0: break
            avail = -depth.sell_orders[ask_p]
            if avail <= 0: continue
            room = max(0, limit - positions[product])
            qty = min(order.quantity, avail, room)
            if qty <= 0: break
            positions[product] += qty; cash[product] -= qty * ask_p
            order.quantity -= qty
            rem = avail - qty
            if rem > 0: depth.sell_orders[ask_p] = -rem
            else: del depth.sell_orders[ask_p]
    elif order.quantity < 0:
        for bid_p in sorted(list(depth.buy_orders.keys()), reverse=True):
            if order.price > bid_p or order.quantity >= 0: break
            avail = depth.buy_orders[bid_p]
            if avail <= 0: continue
            room = max(0, limit + positions[product])
            qty = min(-order.quantity, avail, room)
            if qty <= 0: break
            positions[product] -= qty; cash[product] += qty * bid_p
            order.quantity += qty
            rem = avail - qty
            if rem > 0: depth.buy_orders[bid_p] = rem
            else: del depth.buy_orders[bid_p]
    return order.quantity


def apply_passive_fills(passive_orders, trades_this_tick, depth_prev, positions, cash, product, limit):
    if not passive_orders or not trades_this_tick: return
    our_buys = {}; our_sells = {}
    for o in passive_orders:
        if o.quantity > 0: our_buys[o.price] = our_buys.get(o.price, 0) + o.quantity
        elif o.quantity < 0: our_sells[o.price] = our_sells.get(o.price, 0) + (-o.quantity)
    book_bb = max(depth_prev.buy_orders.keys()) if depth_prev and depth_prev.buy_orders else None
    book_ba = min(depth_prev.sell_orders.keys()) if depth_prev and depth_prev.sell_orders else None
    for tr in trades_this_tick:
        tp = tr.price; tv = abs(tr.quantity)
        if tv <= 0: continue
        is_buy = (book_ba is not None and tp >= book_ba)
        is_sell = (book_bb is not None and tp <= book_bb)
        if not is_buy and not is_sell:
            if any(p <= tp and our_sells[p] > 0 for p in our_sells): is_buy = True
            elif any(p >= tp and our_buys[p] > 0 for p in our_buys): is_sell = True
        if is_buy:
            rem_tv = tv
            for p in sorted(our_sells.keys()):
                if rem_tv <= 0 or p > tp: break
                our_qty = our_sells[p]
                if our_qty <= 0: continue
                if book_ba is None or p < book_ba: fill = min(our_qty, rem_tv)
                else:
                    book_at_p = -depth_prev.sell_orders.get(p, 0) if depth_prev else 0
                    total = our_qty + book_at_p
                    fill = min(our_qty, int(round(rem_tv * our_qty / total))) if total > 0 else 0
                room = limit + positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] -= fill; cash[product] += fill * p
                    our_sells[p] = our_qty - fill; rem_tv -= fill
        elif is_sell:
            rem_tv = tv
            for p in sorted(our_buys.keys(), reverse=True):
                if rem_tv <= 0 or p < tp: break
                our_qty = our_buys[p]
                if our_qty <= 0: continue
                if book_bb is None or p > book_bb: fill = min(our_qty, rem_tv)
                else:
                    book_at_p = depth_prev.buy_orders.get(p, 0) if depth_prev else 0
                    total = our_qty + book_at_p
                    fill = min(our_qty, int(round(rem_tv * our_qty / total))) if total > 0 else 0
                room = limit - positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] += fill; cash[product] -= fill * p
                    our_buys[p] = our_qty - fill; rem_tv -= fill


def simulate(day):
    snapshots = load_prices(day)
    trades_by_ts = load_trades(day)
    trader = trader_module.Trader()
    positions = defaultdict(int); cash = defaultdict(float); trader_data = ""
    listings = {p: Listing(p, p, "SEASHELLS") for p in PRODUCTS}
    timestamps = sorted(snapshots.keys())
    pending_passive = {p: [] for p in PRODUCTS}
    pending_depth = {p: None for p in PRODUCTS}
    prev_market_trades = {p: [] for p in PRODUCTS}
    for ts in timestamps:
        depths = snapshots[ts]
        for p in PRODUCTS:
            if pending_passive[p]:
                trades_now = trades_by_ts.get(ts, {}).get(p, [])
                apply_passive_fills(pending_passive[p], trades_now, pending_depth[p],
                                    positions, cash, p, trader_module.POSITION_LIMIT)
        pending_passive = {p: [] for p in PRODUCTS}
        state = TradingState(traderData=trader_data, timestamp=ts, listings=listings,
                             order_depths=depths, own_trades={p: [] for p in PRODUCTS},
                             market_trades=prev_market_trades, position=dict(positions),
                             observations=None)
        try: result, _, trader_data = trader.run(state)
        except Exception:
            prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue
        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None: continue
            dm = OrderDepth(); dm.buy_orders = dict(depth.buy_orders); dm.sell_orders = dict(depth.sell_orders)
            passive = []
            for order in orders:
                rem = fill_crossing(order, dm, positions, cash, product, trader_module.POSITION_LIMIT)
                if rem != 0: passive.append(Order(order.symbol, order.price, rem))
            pending_passive[product] = passive; pending_depth[product] = dm
        prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
    last_ts = timestamps[-1]; final_pnl = {}
    for p in PRODUCTS:
        depth = snapshots[last_ts].get(p)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        elif depth and depth.buy_orders: mid = max(depth.buy_orders)
        elif depth and depth.sell_orders: mid = min(depth.sell_orders)
        else: mid = 0
        final_pnl[p] = cash[p] + positions[p] * mid
    return final_pnl


def run_cycling(overrides):
    """Run 3 days with Pepper cycling params."""
    saved = dict(trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"])
    trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"].update(overrides)
    total = defaultdict(float); per_day = {}
    for day in DAYS:
        pnl = simulate(day); per_day[day] = pnl
        for p in PRODUCTS: total[p] += pnl[p]
    grand = sum(total.values())
    trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"] = saved
    return grand, total, per_day


def main():
    # Baseline (cycling OFF)
    baseline, bt, bd = run_cycling({"enable_cycling": False})
    print(f"[BASELINE cycling OFF] TOTAL={baseline:+.0f}  (Osm={bt['ASH_COATED_OSMIUM']:+.0f} Pep={bt['INTARIAN_PEPPER_ROOT']:+.0f})")
    print(f"  day-1={sum(bd[-1].values()):+.0f}  day0={sum(bd[0].values()):+.0f}  day+1={sum(bd[1].values()):+.0f}")
    print()

    # Default cycling ON (20/-15/20/40/300)
    print("=== STEP 1 : Default cycling ON ===")
    grand, tot, pd = run_cycling({"enable_cycling": True})
    delta = grand - baseline
    print(f"  TOTAL={grand:+.0f}  delta={delta:+.0f}  (Osm={tot['ASH_COATED_OSMIUM']:+.0f} Pep={tot['INTARIAN_PEPPER_ROOT']:+.0f})")
    print(f"  day-1={sum(pd[-1].values()):+.0f}  day0={sum(pd[0].values()):+.0f}  day+1={sum(pd[1].values()):+.0f}")

    # Grid sell_trigger
    print("\n=== GRID : cycle_sell_trigger ===")
    print(f"{'trig':>5} {'Total':>10} {'Delta':>8} {'d-1':>8} {'d0':>8} {'d+1':>8}")
    for st in [5, 10, 15, 20, 25, 30, 40, 50]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_sell_trigger": st})
        d = g - baseline
        print(f"{st:>5} {g:>+10.0f} {d:>+8.0f} {sum(pd[-1].values()):>+8.0f} {sum(pd[0].values()):>+8.0f} {sum(pd[1].values()):>+8.0f}")

    # Grid buy_trigger
    print("\n=== GRID : cycle_buy_trigger ===")
    print(f"{'trig':>5} {'Total':>10} {'Delta':>8}")
    for bt_ in [-5, -10, -15, -20, -25, -30, -40]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_buy_trigger": bt_})
        d = g - baseline
        print(f"{bt_:>5} {g:>+10.0f} {d:>+8.0f}")

    # Grid sell_qty
    print("\n=== GRID : cycle_sell_qty ===")
    print(f"{'qty':>5} {'Total':>10} {'Delta':>8}")
    for sq in [5, 10, 20, 30, 40, 60, 80]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_sell_qty": sq, "cycle_buy_qty": sq})
        d = g - baseline
        print(f"{sq:>5} {g:>+10.0f} {d:>+8.0f}")

    # Grid hold_min
    print("\n=== GRID : cycle_hold_min ===")
    print(f"{'hmin':>5} {'Total':>10} {'Delta':>8}")
    for hm in [0, 10, 20, 30, 40, 50, 60]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_hold_min": hm})
        d = g - baseline
        print(f"{hm:>5} {g:>+10.0f} {d:>+8.0f}")

    # Grid cooldown
    print("\n=== GRID : cycle_cooldown ===")
    print(f"{'cd':>5} {'Total':>10} {'Delta':>8}")
    for cd in [100, 200, 300, 500, 1000, 2000, 5000]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_cooldown": cd})
        d = g - baseline
        print(f"{cd:>5} {g:>+10.0f} {d:>+8.0f}")

    # Grid ma_window
    print("\n=== GRID : cycle_ma_window ===")
    print(f"{'win':>5} {'Total':>10} {'Delta':>8}")
    for w in [10, 20, 30, 50, 75, 100]:
        g, t, pd = run_cycling({"enable_cycling": True, "cycle_ma_window": w})
        d = g - baseline
        print(f"{w:>5} {g:>+10.0f} {d:>+8.0f}")


if __name__ == "__main__":
    main()
