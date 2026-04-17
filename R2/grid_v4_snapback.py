"""Grid search threshold + qty + hold_min pour snap-back v4."""
import sys, os, copy
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "R1")))

import trader_r2_v4 as tm
from local_backtest_r2 import simulate as _sim_v31
from datamodel import OrderDepth, TradingState, Order, Listing, Trade

# Custom simulate using v4 trader
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
            for i in (1,2,3):
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
            prod = row["symbol"]; price = int(float(row["price"])); qty = int(row["quantity"])
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
            order.quantity -= qty; rem = avail - qty
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
            order.quantity += qty; rem = avail - qty
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
                q = our_sells[p]
                if q <= 0: continue
                if book_ba is None or p < book_ba: fill = min(q, rem_tv)
                else:
                    ba_p = -depth_prev.sell_orders.get(p, 0) if depth_prev else 0
                    total = q + ba_p
                    fill = min(q, int(round(rem_tv * q / total))) if total > 0 else 0
                room = limit + positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] -= fill; cash[product] += fill * p
                    our_sells[p] = q - fill; rem_tv -= fill
        elif is_sell:
            rem_tv = tv
            for p in sorted(our_buys.keys(), reverse=True):
                if rem_tv <= 0 or p < tp: break
                q = our_buys[p]
                if q <= 0: continue
                if book_bb is None or p > book_bb: fill = min(q, rem_tv)
                else:
                    bb_p = depth_prev.buy_orders.get(p, 0) if depth_prev else 0
                    total = q + bb_p
                    fill = min(q, int(round(rem_tv * q / total))) if total > 0 else 0
                room = limit - positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] += fill; cash[product] -= fill * p
                    our_buys[p] = q - fill; rem_tv -= fill

def simulate_v4(day):
    snapshots = load_prices(day); trades_by_ts = load_trades(day)
    trader = tm.Trader()
    positions = defaultdict(int); cash = defaultdict(float); trader_data = ""
    listings = {p: Listing(p, p, "SEASHELLS") for p in PRODUCTS}
    timestamps = sorted(snapshots.keys())
    pending_passive = {p: [] for p in PRODUCTS}; pending_depth = {p: None for p in PRODUCTS}
    prev_mt = {p: [] for p in PRODUCTS}
    for ts in timestamps:
        depths = snapshots[ts]
        for p in PRODUCTS:
            if pending_passive[p]:
                trades_now = trades_by_ts.get(ts, {}).get(p, [])
                apply_passive_fills(pending_passive[p], trades_now, pending_depth[p], positions, cash, p, tm.POSITION_LIMIT)
        pending_passive = {p: [] for p in PRODUCTS}
        state = TradingState(traderData=trader_data, timestamp=ts, listings=listings,
                             order_depths=depths, own_trades={p: [] for p in PRODUCTS},
                             market_trades=prev_mt, position=dict(positions), observations=None)
        try: result, _, trader_data = trader.run(state)
        except Exception:
            prev_mt = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue
        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None: continue
            dm = OrderDepth(); dm.buy_orders = dict(depth.buy_orders); dm.sell_orders = dict(depth.sell_orders)
            passive = []
            for order in orders:
                rem = fill_crossing(order, dm, positions, cash, product, tm.POSITION_LIMIT)
                if rem != 0: passive.append(Order(order.symbol, order.price, rem))
            pending_passive[product] = passive; pending_depth[product] = dm
        prev_mt = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
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


def run(overrides):
    saved = dict(tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"])
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"].update(overrides)
    total = defaultdict(float)
    for day in DAYS:
        pnl = simulate_v4(day)
        for p in PRODUCTS: total[p] += pnl[p]
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"] = saved
    return sum(total.values()), total

# Baseline (OFF)
BASELINE = 27097

import sys
# Suppress prints from trader
import io
class NullIO(io.StringIO):
    def write(self, *a, **kw): pass
old_stdout = sys.stdout

def run_silent(overrides):
    sys.stdout = NullIO()
    try:
        r = run(overrides)
    finally:
        sys.stdout = old_stdout
    return r


print(f"BASELINE (cycling OFF) = {BASELINE}\n")

# Test 1: cycling ON with default params
g, t = run_silent({"snap_back_enabled": True})
print(f"DEFAULT cycling ON : {g:+.0f}  delta={g-BASELINE:+.0f}  Pep={t['INTARIAN_PEPPER_ROOT']:+.0f}")

print("\n=== GRID threshold (qty=20, hold_min=40) ===")
print(f"{'thr':>5} {'Total':>9} {'Pep':>9} {'Delta':>8}")
for thr in [5, 6, 7, 8, 10, 12, 15, 20]:
    g, t = run_silent({"snap_back_enabled": True, "snap_back_threshold": thr})
    print(f"{thr:>5} {g:>+9.0f} {t['INTARIAN_PEPPER_ROOT']:>+9.0f} {g-BASELINE:>+8.0f}")

print("\n=== GRID qty (threshold=5, hold_min=40) ===")
print(f"{'qty':>5} {'Total':>9} {'Pep':>9} {'Delta':>8}")
for qty in [5, 10, 15, 20, 30, 40, 60]:
    g, t = run_silent({"snap_back_enabled": True, "snap_back_qty": qty})
    print(f"{qty:>5} {g:>+9.0f} {t['INTARIAN_PEPPER_ROOT']:>+9.0f} {g-BASELINE:>+8.0f}")

print("\n=== GRID hold_min (threshold=5, qty=20) ===")
print(f"{'hmin':>5} {'Total':>9} {'Pep':>9} {'Delta':>8}")
for hm in [0, 20, 30, 40, 50, 60, 70]:
    g, t = run_silent({"snap_back_enabled": True, "snap_back_hold_min": hm})
    print(f"{hm:>5} {g:>+9.0f} {t['INTARIAN_PEPPER_ROOT']:>+9.0f} {g-BASELINE:>+8.0f}")

print("\n=== GRID threshold high (qty=40, hold_min=20) ===")
for thr in [5, 6, 8, 10, 12, 15, 20, 30]:
    g, t = run_silent({"snap_back_enabled": True, "snap_back_threshold": thr, "snap_back_qty": 40, "snap_back_hold_min": 20})
    print(f"thr={thr:>3} qty=40 hmin=20: {g:>+9.0f}  delta={g-BASELINE:>+6.0f}")
