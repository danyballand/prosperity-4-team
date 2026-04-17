"""
Variante du backtester R2 avec simulation du MAF (+25% volume).

Approximation : multiplie les volumes bid/ask du book par 1.25 avant simulation.
Pas parfait (le +25% IMC est en réalité des quotes EXTRA, pas un scaling), mais
donne un upper bound raisonnable de l'EV du MAF.

Usage :
  python3 local_backtest_r2_maf.py            # baseline (pas de MAF)
  python3 local_backtest_r2_maf.py maf        # avec +25% volume
  python3 local_backtest_r2_maf.py v32        # v32 baseline
  python3 local_backtest_r2_maf.py v32 maf    # v32 + MAF
"""
import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
R1_DIR = os.path.abspath(os.path.join(HERE, "..", "R1"))
sys.path.insert(0, R1_DIR)

from datamodel import OrderDepth, TradingState, Order, Listing, Trade

args = sys.argv[1:]
USE_V32 = "v32" in args
USE_MAF = "maf" in args
USE_R2 = "r2" in args

if USE_R2:
    # Importer depuis R2/ (même dir que ce script)
    sys.path.insert(0, HERE)
    import trader_r2 as trader_module
    TRADER_LABEL = "trader_r2 (v31+bid=300)"
elif USE_V32:
    import trader_v32 as trader_module
    TRADER_LABEL = "v32"
else:
    import trader as trader_module
    TRADER_LABEL = "v31"

MAF_LABEL = "MAF +25%" if USE_MAF else "baseline"
Trader = trader_module.Trader
POSITION_LIMIT = trader_module.POSITION_LIMIT

DATA_DIR = os.path.join(HERE, "data")
DAYS = [-1, 0, 1]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]
LIVE_DURATION_TS = 100_000
MAF_MULTIPLIER = 1.25 if USE_MAF else 1.0


def load_prices(day, max_ts=LIVE_DURATION_TS):
    path = os.path.join(DATA_DIR, f"prices_round_2_day_{day}.csv")
    snapshots = defaultdict(dict)
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if max_ts is not None and ts >= max_ts:
                continue
            p = row["product"]
            od = OrderDepth()
            for i in (1, 2, 3):
                bp = row.get(f"bid_price_{i}", "")
                bv = row.get(f"bid_volume_{i}", "")
                ap = row.get(f"ask_price_{i}", "")
                av = row.get(f"ask_volume_{i}", "")
                if bp and bv:
                    od.buy_orders[int(bp)] = int(round(int(bv) * MAF_MULTIPLIER))
                if ap and av:
                    od.sell_orders[int(ap)] = -int(round(int(av) * MAF_MULTIPLIER))
            snapshots[ts][p] = od
    return snapshots


def load_trades(day, max_ts=LIVE_DURATION_TS):
    path = os.path.join(DATA_DIR, f"trades_round_2_day_{day}.csv")
    trades_by_ts = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if max_ts is not None and ts >= max_ts:
                continue
            prod = row["symbol"]
            price = int(float(row["price"]))
            qty = int(round(int(row["quantity"]) * MAF_MULTIPLIER))
            tr = Trade(symbol=prod, price=price, quantity=qty, buyer="", seller="",
                       timestamp=ts)
            trades_by_ts[ts][prod].append(tr)
    return trades_by_ts


def fill_crossing(order, depth, positions, cash, product, limit):
    if order.quantity > 0:
        for ask_p in sorted(list(depth.sell_orders.keys())):
            if order.price < ask_p or order.quantity <= 0:
                break
            avail = -depth.sell_orders[ask_p]
            if avail <= 0:
                continue
            room = max(0, limit - positions[product])
            qty = min(order.quantity, avail, room)
            if qty <= 0:
                break
            positions[product] += qty
            cash[product] -= qty * ask_p
            order.quantity -= qty
            remaining_at_level = avail - qty
            if remaining_at_level > 0:
                depth.sell_orders[ask_p] = -remaining_at_level
            else:
                del depth.sell_orders[ask_p]
    elif order.quantity < 0:
        for bid_p in sorted(list(depth.buy_orders.keys()), reverse=True):
            if order.price > bid_p or order.quantity >= 0:
                break
            avail = depth.buy_orders[bid_p]
            if avail <= 0:
                continue
            room = max(0, limit + positions[product])
            qty = min(-order.quantity, avail, room)
            if qty <= 0:
                break
            positions[product] -= qty
            cash[product] += qty * bid_p
            order.quantity += qty
            remaining_at_level = avail - qty
            if remaining_at_level > 0:
                depth.buy_orders[bid_p] = remaining_at_level
            else:
                del depth.buy_orders[bid_p]
    return order.quantity


def apply_passive_fills(passive_orders, trades_this_tick, depth_prev, positions, cash, product, limit):
    if not passive_orders or not trades_this_tick:
        return
    our_buys = {}
    our_sells = {}
    for o in passive_orders:
        if o.quantity > 0:
            our_buys[o.price] = our_buys.get(o.price, 0) + o.quantity
        elif o.quantity < 0:
            our_sells[o.price] = our_sells.get(o.price, 0) + (-o.quantity)
    book_bb = max(depth_prev.buy_orders.keys()) if depth_prev and depth_prev.buy_orders else None
    book_ba = min(depth_prev.sell_orders.keys()) if depth_prev and depth_prev.sell_orders else None
    for tr in trades_this_tick:
        tp = tr.price
        tv = abs(tr.quantity)
        if tv <= 0:
            continue
        is_buy_candidate = (book_ba is not None and tp >= book_ba)
        is_sell_candidate = (book_bb is not None and tp <= book_bb)
        if not is_buy_candidate and not is_sell_candidate:
            our_better_sells = [p for p in our_sells if p <= tp and our_sells[p] > 0]
            if our_better_sells:
                is_buy_candidate = True
            else:
                our_better_buys = [p for p in our_buys if p >= tp and our_buys[p] > 0]
                if our_better_buys:
                    is_sell_candidate = True
        if is_buy_candidate:
            remaining_tv = tv
            for p in sorted(our_sells.keys()):
                if remaining_tv <= 0:
                    break
                if p > tp:
                    break
                our_qty = our_sells[p]
                if our_qty <= 0:
                    continue
                if book_ba is None or p < book_ba:
                    fill = min(our_qty, remaining_tv)
                else:
                    book_at_p = -depth_prev.sell_orders.get(p, 0) if depth_prev else 0
                    total = our_qty + book_at_p
                    fill = min(our_qty, int(round(remaining_tv * our_qty / total))) if total > 0 else 0
                room = limit + positions[product]
                fill = min(fill, room)
                if fill > 0:
                    positions[product] -= fill
                    cash[product] += fill * p
                    our_sells[p] = our_qty - fill
                    remaining_tv -= fill
        elif is_sell_candidate:
            remaining_tv = tv
            for p in sorted(our_buys.keys(), reverse=True):
                if remaining_tv <= 0:
                    break
                if p < tp:
                    break
                our_qty = our_buys[p]
                if our_qty <= 0:
                    continue
                if book_bb is None or p > book_bb:
                    fill = min(our_qty, remaining_tv)
                else:
                    book_at_p = depth_prev.buy_orders.get(p, 0) if depth_prev else 0
                    total = our_qty + book_at_p
                    fill = min(our_qty, int(round(remaining_tv * our_qty / total))) if total > 0 else 0
                room = limit - positions[product]
                fill = min(fill, room)
                if fill > 0:
                    positions[product] += fill
                    cash[product] -= fill * p
                    our_buys[p] = our_qty - fill
                    remaining_tv -= fill


def simulate(day, max_ts=LIVE_DURATION_TS):
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

    for ts in timestamps:
        depths = snapshots[ts]
        for p in PRODUCTS:
            if pending_passive[p]:
                trades_now = trades_by_ts.get(ts, {}).get(p, [])
                apply_passive_fills(pending_passive[p], trades_now, pending_depth[p],
                                    positions, cash, p, POSITION_LIMIT)
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
            if depth is None:
                continue
            depth_mutable = OrderDepth()
            depth_mutable.buy_orders = dict(depth.buy_orders)
            depth_mutable.sell_orders = dict(depth.sell_orders)
            passive_orders_this_product = []
            for order in orders:
                remaining = fill_crossing(order, depth_mutable, positions, cash, product, POSITION_LIMIT)
                if remaining != 0:
                    passive_orders_this_product.append(Order(order.symbol, order.price, remaining))
            pending_passive[product] = passive_orders_this_product
            pending_depth[product] = depth_mutable
        prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}

    last_ts = timestamps[-1]
    final_pnl = {}
    for p in PRODUCTS:
        depth = snapshots[last_ts].get(p)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        elif depth and depth.buy_orders:
            mid = max(depth.buy_orders)
        elif depth and depth.sell_orders:
            mid = min(depth.sell_orders)
        else:
            mid = 0
        final_pnl[p] = cash[p] + positions[p] * mid
    return final_pnl


if __name__ == "__main__":
    print(f"=== BACKTEST R2 — {TRADER_LABEL} / {MAF_LABEL} ===\n")
    total = defaultdict(float)
    for day in DAYS:
        pnl = simulate(day)
        print(f"Day {day:+d}: Osm {pnl['ASH_COATED_OSMIUM']:+9.1f}  Pep {pnl['INTARIAN_PEPPER_ROOT']:+9.1f}  Total {sum(pnl.values()):+9.1f}")
        for p in PRODUCTS:
            total[p] += pnl[p]
    print(f"\n3-jours: Osm {total['ASH_COATED_OSMIUM']:+.1f}  Pep {total['INTARIAN_PEPPER_ROOT']:+.1f}  GRAND {sum(total.values()):+.1f}")
