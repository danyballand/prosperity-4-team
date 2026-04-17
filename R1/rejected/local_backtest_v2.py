"""
Backtester v2 — corrige 2 bugs du v1 :

1. Truncate à ts ≤ 100_000 par défaut (= durée réelle du live, vs 1M dans le CSV)
2. Passive fill model : nos ordres MAKE qui ne crossent pas sont fillés
   pro-rata avec le book quand un trade arrive à leur niveau ou mieux

Validation cible : backtest day 0 ≈ 12k ± 1k (live = 12,159).
"""
import csv
import os
from collections import defaultdict
from datamodel import OrderDepth, TradingState, Order, Listing, Trade
from trader import Trader, POSITION_LIMIT

DATA_DIR = os.path.join(os.path.dirname(__file__), "ROUND_1")
DAYS = [-2, -1, 0]
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]
LIVE_DURATION_TS = 100_000  # même durée que le live


def load_prices(day, max_ts=LIVE_DURATION_TS):
    path = os.path.join(DATA_DIR, f"prices_round_1_day_{day}.csv")
    snapshots = defaultdict(dict)
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if max_ts is not None and ts > max_ts:
                continue
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


def load_trades(day, max_ts=LIVE_DURATION_TS):
    """Charge trades CSV → dict[ts] → dict[product] → list of Trade objects."""
    path = os.path.join(DATA_DIR, f"trades_round_1_day_{day}.csv")
    if not os.path.exists(path):
        # try alt location (Downloads)
        alt = os.path.expanduser(f"~/Downloads/ROUND1/trades_round_1_day_{day}.csv")
        if os.path.exists(alt):
            path = alt
        else:
            print(f"WARNING: trades CSV introuvable pour day {day}, passive fills désactivés")
            return {}
    trades_by_ts = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            if max_ts is not None and ts > max_ts:
                continue
            prod = row["symbol"]
            price = int(float(row["price"]))
            qty = int(row["quantity"])
            # Trade object compatible (buyer/seller vides en 2026)
            tr = Trade(symbol=prod, price=price, quantity=qty, buyer="", seller="",
                       timestamp=ts)
            trades_by_ts[ts][prod].append(tr)
    return trades_by_ts


def fill_crossing(order, depth, positions, cash, product, limit):
    """Remplit les parties de l'ordre qui croisent le book existant. Retourne qty restante passive."""
    if order.quantity > 0:  # BUY
        for ask_p in sorted(depth.sell_orders.keys()):
            if order.price >= ask_p:
                avail = -depth.sell_orders[ask_p]
                qty = min(order.quantity, avail)
                if qty > 0 and positions[product] + qty <= limit:
                    positions[product] += qty
                    cash[product] -= qty * ask_p
                    order.quantity -= qty
                if order.quantity <= 0:
                    break
            else:
                break
    elif order.quantity < 0:  # SELL
        for bid_p in sorted(depth.buy_orders.keys(), reverse=True):
            if order.price <= bid_p:
                avail = depth.buy_orders[bid_p]
                qty = min(-order.quantity, avail)
                if qty > 0 and positions[product] - qty >= -limit:
                    positions[product] -= qty
                    cash[product] += qty * bid_p
                    order.quantity += qty
                if order.quantity >= 0:
                    break
            else:
                break
    return order.quantity  # qty passive restante (signée)


def apply_passive_fills(passive_orders, trades_this_tick, depth, positions, cash, product, limit):
    """
    Simule les fills passifs via les trades CSV.
    Modèle per-level : chaque trade à price tp consomme niveau tp seulement
    (pas de cascade multi-niveaux, car la CSV report chaque level séparément).

    Détermination du side :
    - effective_best_bid = max(book_bb, max(our_buys)) si on a amélioré
    - effective_best_ask = min(book_ba, min(our_sells)) si on a amélioré
    - tp >= effective_best_ask → market buy → hit nos SELLs à tp
    - tp <= effective_best_bid → market sell → hit nos BUYs à tp
    - Sinon (inside spread) : on vérifie les 2 cas (post-improve)
    """
    if not passive_orders or not trades_this_tick:
        return

    our_buys = {}
    our_sells = {}
    for o in passive_orders:
        if o.quantity > 0:
            our_buys[o.price] = our_buys.get(o.price, 0) + o.quantity
        elif o.quantity < 0:
            our_sells[o.price] = our_sells.get(o.price, 0) + (-o.quantity)

    book_bb = max(depth.buy_orders.keys()) if depth.buy_orders else None
    book_ba = min(depth.sell_orders.keys()) if depth.sell_orders else None
    our_best_buy = max(our_buys.keys()) if our_buys else None
    our_best_sell = min(our_sells.keys()) if our_sells else None
    effective_bb = max(x for x in [book_bb, our_best_buy] if x is not None) if (book_bb or our_best_buy) else None
    effective_ba = min(x for x in [book_ba, our_best_sell] if x is not None) if (book_ba or our_best_sell) else None

    for tr in trades_this_tick:
        tp = tr.price
        tv = abs(tr.quantity)

        # Trade classification : essaie d'abord market buy, puis market sell
        # per-level matching : consume only level = tp
        tried = False

        # Hypothèse 1 : market buy hit asks au niveau tp
        if effective_ba is not None and tp >= effective_ba:
            our_at_tp = our_sells.get(tp, 0)
            book_at_tp = -depth.sell_orders.get(tp, 0)
            total = our_at_tp + book_at_tp
            if total > 0 and our_at_tp > 0:
                our_share = min(our_at_tp, int(round(tv * our_at_tp / total)))
                if our_share > 0 and positions[product] - our_share >= -limit:
                    positions[product] -= our_share
                    cash[product] += our_share * tp
                    our_sells[tp] = our_at_tp - our_share
                    tried = True

        # Hypothèse 2 : market sell hit bids au niveau tp
        # Note: si tp est dans le spread et on a BUY amélioré à tp, on capture ici
        if not tried and effective_bb is not None and tp <= effective_bb:
            our_at_tp = our_buys.get(tp, 0)
            book_at_tp = depth.buy_orders.get(tp, 0)
            total = our_at_tp + book_at_tp
            if total > 0 and our_at_tp > 0:
                our_share = min(our_at_tp, int(round(tv * our_at_tp / total)))
                if our_share > 0 and positions[product] + our_share <= limit:
                    positions[product] += our_share
                    cash[product] -= our_share * tp
                    our_buys[tp] = our_at_tp - our_share

        # Cas "inside spread" (trade entre book_bb et book_ba, ni amélioré par nous)
        # Pas de fill possible — le trade s'est fait hors book visible


def simulate(day, max_ts=LIVE_DURATION_TS, passive_fills=True, verbose=False):
    snapshots = load_prices(day, max_ts)
    trades_by_ts = load_trades(day, max_ts) if passive_fills else {}
    trader = Trader()
    positions = defaultdict(int)
    cash = defaultdict(float)
    trader_data = ""
    listings = {p: Listing(p, p, "SEASHELLS") for p in PRODUCTS}
    timestamps = sorted(snapshots.keys())

    fills_taken = defaultdict(int)
    fills_passive = defaultdict(int)

    for ts in timestamps:
        depths = snapshots[ts]
        market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
        state = TradingState(
            traderData=trader_data,
            timestamp=ts,
            listings=listings,
            order_depths=depths,
            own_trades={p: [] for p in PRODUCTS},
            market_trades=market_trades,
            position=dict(positions),
            observations=None,
        )
        try:
            result, _, trader_data = trader.run(state)
        except Exception as e:
            if verbose:
                print(f"t={ts} ERROR: {e}")
            continue

        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None:
                continue
            pos_before = positions[product]
            passive_orders = []
            for order in orders:
                # Fill crossing first
                remaining = fill_crossing(order, depth, positions, cash, product, POSITION_LIMIT)
                if remaining != 0:
                    # Ordre passif restant
                    passive_orders.append(Order(order.symbol, order.price, remaining))
            pos_after_take = positions[product]
            fills_taken[product] += abs(pos_after_take - pos_before)

            # Fill passifs via trades CSV
            if passive_fills and passive_orders:
                apply_passive_fills(passive_orders, market_trades[product],
                                     depth, positions, cash, product, POSITION_LIMIT)
                pos_after_passive = positions[product]
                fills_passive[product] += abs(pos_after_passive - pos_after_take)

    # Mark-to-market final
    last_ts = timestamps[-1]
    final_pnl = {}
    for p in PRODUCTS:
        depth = snapshots[last_ts].get(p)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        else:
            mid = 0
        final_pnl[p] = cash[p] + positions[p] * mid
    return final_pnl, dict(positions), dict(fills_taken), dict(fills_passive)


if __name__ == "__main__":
    print(f"=== BACKTEST V2 (truncated ts<={LIVE_DURATION_TS}, passive fills ON) ===\n")
    total = defaultdict(float)
    for day in DAYS:
        pnl, pos, ft, fp = simulate(day, passive_fills=True)
        print(f"--- Day {day} ---")
        for p in PRODUCTS:
            print(f"  {p:<25} PnL={pnl[p]:+8.1f}  pos={pos[p]:+4d}  fills_take={ft.get(p,0):>4}  fills_passive={fp.get(p,0):>4}")
            total[p] += pnl[p]
    print("\n=== TOTAL 3 jours ===")
    for p in PRODUCTS:
        print(f"  {p:<25} {total[p]:+8.1f}")
    grand = sum(total.values())
    print(f"  GRAND TOTAL: {grand:+.1f}")
    print(f"\n  Rappel LIVE (day 0 seul): Osm=+4716  Pep=+7443  Total=+12,159")
