"""
Backtester Round 3 — 12 produits (HYDROGEL_PACK, VELVETFRUIT_EXTRACT, 10 VEVs).

Différences clé vs R2 :
  - 3 jours de data (0, 1, 2)
  - fichiers prices_round_3_day_*.csv / trades_round_3_day_*.csv
  - limites de position PAR PRODUIT (lues depuis PRODUCT_PARAMS du trader)
  - PnL affiché par produit (pas juste Osm/Pep)

Usage :
  python3 local_backtest_r3.py              # trader_r3.py
  python3 local_backtest_r3.py maf          # + MAF scaling (si on garde le bid)
"""
import csv
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from datamodel import OrderDepth, TradingState, Order, Listing, Trade

args = sys.argv[1:]
USE_MAF = "maf" in args

# Trader module (par défaut trader_r3.py, peut être override plus tard)
import trader_r3 as trader_module
TRADER_LABEL = "trader_r3 (12 produits R3)"

MAF_LABEL = "MAF +25%" if USE_MAF else "baseline"
Trader = trader_module.Trader
PRODUCT_PARAMS = trader_module.PRODUCT_PARAMS
DEFAULT_PARAMS = trader_module.DEFAULT_PARAMS

DATA_DIR = os.path.join(HERE, "data")
DAYS = [0, 1, 2]
PRODUCTS = [
    "HYDROGEL_PACK",
    "VELVETFRUIT_EXTRACT",
    "VEV_4000", "VEV_4500", "VEV_5000", "VEV_5100", "VEV_5200",
    "VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500",
]
LIVE_DURATION_TS = 1_000_000  # R3 : 3 jours, 1M timestamps par jour
MAF_MULTIPLIER = 1.25 if USE_MAF else 1.0


def _limit_for(product: str) -> int:
    """Position limit lu depuis PRODUCT_PARAMS du trader."""
    params = PRODUCT_PARAMS.get(product, DEFAULT_PARAMS)
    return int(params.get("position_limit", 80))


def load_prices(day, max_ts=LIVE_DURATION_TS):
    path = os.path.join(DATA_DIR, f"prices_round_3_day_{day}.csv")
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
    path = os.path.join(DATA_DIR, f"trades_round_3_day_{day}.csv")
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
                                    positions, cash, p, _limit_for(p))
        pending_passive = {p: [] for p in PRODUCTS}

        state = TradingState(
            traderData=trader_data, timestamp=ts, listings=listings,
            order_depths=depths, own_trades={p: [] for p in PRODUCTS},
            market_trades=prev_market_trades, position=dict(positions), observations=None,
        )
        try:
            result, _, trader_data = trader.run(state)
        except Exception as e:
            print(f"ERR day={day} ts={ts} trader.run: {type(e).__name__}:{e}")
            prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue

        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None:
                continue
            limit = _limit_for(product)
            depth_mutable = OrderDepth()
            depth_mutable.buy_orders = dict(depth.buy_orders)
            depth_mutable.sell_orders = dict(depth.sell_orders)
            passive_orders_this_product = []
            for order in orders:
                remaining = fill_crossing(order, depth_mutable, positions, cash, product, limit)
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


def _short(p: str) -> str:
    """Nom abrégé pour affichage compact."""
    if p == "HYDROGEL_PACK": return "HYD"
    if p == "VELVETFRUIT_EXTRACT": return "VE "
    if p.startswith("VEV_"): return p.replace("VEV_", "V")  # V5400
    return p[:6]


if __name__ == "__main__":
    print(f"=== BACKTEST R3 — {TRADER_LABEL} / {MAF_LABEL} ===")
    print(f"Produits: {len(PRODUCTS)} | Days: {DAYS} | Max_ts: {LIVE_DURATION_TS}")
    print(f"Limits par produit:")
    for p in PRODUCTS:
        print(f"  {_short(p):>6} limit={_limit_for(p)}")
    print()

    total = defaultdict(float)
    for day in DAYS:
        pnl = simulate(day)
        grand = sum(pnl.values())
        parts = "  ".join(f"{_short(p)}{pnl[p]:+7.0f}" for p in PRODUCTS)
        print(f"Day {day}: {parts}  | TOTAL {grand:+8.0f}")
        for p in PRODUCTS:
            total[p] += pnl[p]

    print()
    print("=== CUMUL 3 JOURS ===")
    for p in PRODUCTS:
        print(f"  {_short(p):>6}  {total[p]:+10.1f}")
    print(f"  GRAND TOTAL  {sum(total.values()):+10.1f}")
