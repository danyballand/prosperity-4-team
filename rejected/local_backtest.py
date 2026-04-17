"""
Backtester local ultra-simple qui rejoue les CSV P4 contre notre trader.py.
Modèle de fill simplifié :
 - nos ordres qui CROISENT le book existant sont fillés au prix de l'ordre existant
 - nos ordres passifs (non-crossing) sont fillés si le mid bouge assez au tick suivant
"""
import csv
import json
import os
from collections import defaultdict
from datamodel import OrderDepth, TradingState, Order, Listing
from trader import Trader, POSITION_LIMIT

DATA_DIR = os.path.join(os.path.dirname(__file__), "ROUND_1")
DAYS = [-2, -1, 0]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]


def load_day(day):
    """Charge les snapshots du book pour un jour donné."""
    path = os.path.join(DATA_DIR, f"prices_round_1_day_{day}.csv")
    snapshots = defaultdict(dict)  # timestamp -> product -> OrderDepth
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            p = row["product"]
            od = OrderDepth()
            for i in (1, 2, 3):
                bp = row.get(f"bid_price_{i}", "")
                bv = row.get(f"bid_volume_{i}", "")
                ap = row.get(f"ask_price_{i}", "")
                av = row.get(f"ask_volume_{i}", "")
                if bp and bv:
                    od.buy_orders[int(bp)] = int(bv)
                if ap and av:
                    od.sell_orders[int(ap)] = -int(av)
            snapshots[ts][p] = od
    return snapshots


def simulate(day):
    snapshots = load_day(day)
    trader = Trader()
    positions = defaultdict(int)
    cash = defaultdict(float)
    trader_data = ""
    listings = {p: Listing(p, p, "SEASHELLS") for p in PRODUCTS}
    timestamps = sorted(snapshots.keys())

    for ts in timestamps:
        depths = snapshots[ts]
        state = TradingState(
            traderData=trader_data,
            timestamp=ts,
            listings=listings,
            order_depths=depths,
            own_trades={p: [] for p in PRODUCTS},
            market_trades={p: [] for p in PRODUCTS},
            position=dict(positions),
            observations=None,
        )
        try:
            result, _, trader_data = trader.run(state)
        except Exception as e:
            print(f"t={ts} ERROR: {e}")
            continue

        # Fill model : on fill tout ordre qui croise le book
        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None:
                continue
            for order in orders:
                if order.quantity > 0:  # BUY
                    # check asks
                    for ask_p in sorted(depth.sell_orders.keys()):
                        if order.price >= ask_p:
                            avail = -depth.sell_orders[ask_p]
                            qty = min(order.quantity, avail)
                            if qty > 0 and positions[product] + qty <= POSITION_LIMIT:
                                positions[product] += qty
                                cash[product] -= qty * ask_p
                                order.quantity -= qty
                            if order.quantity <= 0:
                                break
                elif order.quantity < 0:  # SELL
                    for bid_p in sorted(depth.buy_orders.keys(), reverse=True):
                        if order.price <= bid_p:
                            avail = depth.buy_orders[bid_p]
                            qty = min(-order.quantity, avail)
                            if qty > 0 and positions[product] - qty >= -POSITION_LIMIT:
                                positions[product] -= qty
                                cash[product] += qty * bid_p
                                order.quantity += qty
                            if order.quantity >= 0:
                                break

    # Mark-to-market final : on valorise la position au dernier mid
    last_ts = timestamps[-1]
    final_pnl = {}
    for p in PRODUCTS:
        depth = snapshots[last_ts].get(p)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        else:
            mid = 0
        final_pnl[p] = cash[p] + positions[p] * mid
    return final_pnl, dict(positions)


if __name__ == "__main__":
    total = defaultdict(float)
    for day in DAYS:
        pnl, pos = simulate(day)
        print(f"\n=== Day {day} ===")
        for p in PRODUCTS:
            print(f"  {p}: PnL={pnl[p]:+.1f}  final_pos={pos[p]}")
            total[p] += pnl[p]
    print("\n=== TOTAL ===")
    for p in PRODUCTS:
        print(f"  {p}: {total[p]:+.1f}")
    print(f"  GRAND TOTAL: {sum(total.values()):+.1f}")
