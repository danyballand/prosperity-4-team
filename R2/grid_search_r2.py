"""
Grid search fin sur les params critiques v31, sur les CSV R2.

Teste :
  - make_edge Osmium : [92..105] (handoff dit cliff entre 95 et 100 mais jamais 96/98 fins)
  - bootstrap_cap_offset Pepper : [5..15] (handoff dit 9 optimal, jamais fin entre 7/8/10/11)
  - triple_edge ratios Osmium : 55/30/15 vs alternatives

Méthode : monkey-patch PRODUCT_PARAMS avant chaque run isolé.
Reporte PnL par produit + total 3 jours.
"""
import csv
import os
import sys
import copy
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
R1_DIR = os.path.abspath(os.path.join(HERE, "..", "R1"))
sys.path.insert(0, R1_DIR)
sys.path.insert(0, HERE)

from datamodel import OrderDepth, TradingState, Order, Listing, Trade
import trader as trader_module
BASELINE_PARAMS_OSM = copy.deepcopy(trader_module.PRODUCT_PARAMS["ASH_COATED_OSMIUM"])
BASELINE_PARAMS_PEP = copy.deepcopy(trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"])

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
            p = row["product"]
            od = OrderDepth()
            for i in (1, 2, 3):
                bp, bv = row.get(f"bid_price_{i}", ""), row.get(f"bid_volume_{i}", "")
                ap, av = row.get(f"ask_price_{i}", ""), row.get(f"ask_volume_{i}", "")
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


def simulate(day, trader_class, pos_limit):
    snapshots = load_prices(day)
    trades_by_ts = load_trades(day)
    trader = trader_class()
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
                                    positions, cash, p, pos_limit)
        pending_passive = {p: [] for p in PRODUCTS}

        state = TradingState(traderData=trader_data, timestamp=ts, listings=listings,
                             order_depths=depths, own_trades={p: [] for p in PRODUCTS},
                             market_trades=prev_market_trades, position=dict(positions),
                             observations=None)
        try:
            result, _, trader_data = trader.run(state)
        except Exception:
            prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue

        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None: continue
            dm = OrderDepth()
            dm.buy_orders = dict(depth.buy_orders); dm.sell_orders = dict(depth.sell_orders)
            passive = []
            for order in orders:
                rem = fill_crossing(order, dm, positions, cash, product, pos_limit)
                if rem != 0: passive.append(Order(order.symbol, order.price, rem))
            pending_passive[product] = passive; pending_depth[product] = dm
        prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}

    last_ts = timestamps[-1]
    final_pnl = {}
    for p in PRODUCTS:
        depth = snapshots[last_ts].get(p)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
        elif depth and depth.buy_orders: mid = max(depth.buy_orders)
        elif depth and depth.sell_orders: mid = min(depth.sell_orders)
        else: mid = 0
        final_pnl[p] = cash[p] + positions[p] * mid
    return final_pnl


def run_config(label, osm_overrides=None, pep_overrides=None):
    """Applique overrides sur PRODUCT_PARAMS, run 3 jours, restore."""
    # Save & apply
    saved_osm = dict(trader_module.PRODUCT_PARAMS["ASH_COATED_OSMIUM"])
    saved_pep = dict(trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"])
    if osm_overrides:
        trader_module.PRODUCT_PARAMS["ASH_COATED_OSMIUM"].update(osm_overrides)
    if pep_overrides:
        trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"].update(pep_overrides)

    total = defaultdict(float)
    per_day = {}
    for day in DAYS:
        pnl = simulate(day, trader_module.Trader, trader_module.POSITION_LIMIT)
        per_day[day] = pnl
        for p in PRODUCTS:
            total[p] += pnl[p]
    grand = sum(total.values())

    # Restore
    trader_module.PRODUCT_PARAMS["ASH_COATED_OSMIUM"] = saved_osm
    trader_module.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"] = saved_pep

    return grand, total, per_day


def main():
    print("=" * 80)
    print("GRID SEARCH v31 sur CSV R2 — baseline +27,097 (3 jours)")
    print("=" * 80)

    # === BASELINE ===
    grand, total, per_day = run_config("baseline")
    baseline = grand
    print(f"\n[BASELINE] Osm={total['ASH_COATED_OSMIUM']:+.0f}  Pep={total['INTARIAN_PEPPER_ROOT']:+.0f}  TOTAL={grand:+.0f}")
    print(f"           day-1={sum(per_day[-1].values()):+.0f}  day0={sum(per_day[0].values()):+.0f}  day+1={sum(per_day[1].values()):+.0f}")

    # === GRID 1 : make_edge Osmium ===
    print("\n" + "=" * 80)
    print("GRID 1 : make_edge Osmium (baseline=97)")
    print("=" * 80)
    print(f"{'edge':>6} {'Osm':>10} {'Pep':>10} {'Total':>10} {'delta':>8} {'d-1':>8} {'d0':>8} {'d+1':>8}")
    best_edge = 97; best_edge_pnl = baseline
    for edge in [92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 105]:
        g, t, pd = run_config(f"edge={edge}", osm_overrides={"make_edge": edge})
        delta = g - baseline
        print(f"{edge:>6} {t['ASH_COATED_OSMIUM']:>+10.0f} {t['INTARIAN_PEPPER_ROOT']:>+10.0f} {g:>+10.0f} {delta:>+8.0f} "
              f"{sum(pd[-1].values()):>+8.0f} {sum(pd[0].values()):>+8.0f} {sum(pd[1].values()):>+8.0f}")
        if g > best_edge_pnl: best_edge_pnl = g; best_edge = edge

    # === GRID 2 : bootstrap_cap_offset Pepper ===
    print("\n" + "=" * 80)
    print("GRID 2 : bootstrap_cap_offset Pepper (baseline=9)")
    print("=" * 80)
    print(f"{'offs':>6} {'Osm':>10} {'Pep':>10} {'Total':>10} {'delta':>8} {'d-1':>8} {'d0':>8} {'d+1':>8}")
    best_offs = 9; best_offs_pnl = baseline
    for offs in [5, 6, 7, 8, 9, 10, 11, 12, 13, 15]:
        g, t, pd = run_config(f"offs={offs}", pep_overrides={"bootstrap_cap_offset": offs})
        delta = g - baseline
        print(f"{offs:>6} {t['ASH_COATED_OSMIUM']:>+10.0f} {t['INTARIAN_PEPPER_ROOT']:>+10.0f} {g:>+10.0f} {delta:>+8.0f} "
              f"{sum(pd[-1].values()):>+8.0f} {sum(pd[0].values()):>+8.0f} {sum(pd[1].values()):>+8.0f}")
        if g > best_offs_pnl: best_offs_pnl = g; best_offs = offs

    # === GRID 3 : max_bias Pepper ===
    print("\n" + "=" * 80)
    print("GRID 3 : max_bias Pepper (baseline=30)")
    print("=" * 80)
    print(f"{'bias':>6} {'Osm':>10} {'Pep':>10} {'Total':>10} {'delta':>8}")
    best_bias = 30; best_bias_pnl = baseline
    for b in [10, 20, 25, 30, 35, 40, 50]:
        g, t, pd = run_config(f"bias={b}", pep_overrides={"max_bias": b})
        delta = g - baseline
        print(f"{b:>6} {t['ASH_COATED_OSMIUM']:>+10.0f} {t['INTARIAN_PEPPER_ROOT']:>+10.0f} {g:>+10.0f} {delta:>+8.0f}")
        if g > best_bias_pnl: best_bias_pnl = g; best_bias = b

    # === GRID 4 : skew_ticks_per_unit Osmium ===
    print("\n" + "=" * 80)
    print("GRID 4 : skew_ticks_per_unit Osmium (baseline=0.04)")
    print("=" * 80)
    print(f"{'skew':>6} {'Osm':>10} {'Pep':>10} {'Total':>10} {'delta':>8}")
    best_skew = 0.04; best_skew_pnl = baseline
    for sk in [0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10]:
        g, t, pd = run_config(f"skew={sk}", osm_overrides={"skew_ticks_per_unit": sk})
        delta = g - baseline
        print(f"{sk:>6} {t['ASH_COATED_OSMIUM']:>+10.0f} {t['INTARIAN_PEPPER_ROOT']:>+10.0f} {g:>+10.0f} {delta:>+8.0f}")
        if g > best_skew_pnl: best_skew_pnl = g; best_skew = sk

    # === GRID 5 : clearing_threshold Osmium ===
    print("\n" + "=" * 80)
    print("GRID 5 : clearing_threshold Osmium (baseline=0.20)")
    print("=" * 80)
    print(f"{'thr':>6} {'Osm':>10} {'Pep':>10} {'Total':>10} {'delta':>8}")
    best_thr = 0.20; best_thr_pnl = baseline
    for thr in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        g, t, pd = run_config(f"thr={thr}", osm_overrides={"clearing_threshold": thr})
        delta = g - baseline
        print(f"{thr:>6} {t['ASH_COATED_OSMIUM']:>+10.0f} {t['INTARIAN_PEPPER_ROOT']:>+10.0f} {g:>+10.0f} {delta:>+8.0f}")
        if g > best_thr_pnl: best_thr_pnl = g; best_thr = thr

    # === COMBINED BEST ===
    print("\n" + "=" * 80)
    print("COMBINED BEST (si tous les best indépendants stackent)")
    print("=" * 80)
    osm_best = {"make_edge": best_edge, "skew_ticks_per_unit": best_skew, "clearing_threshold": best_thr}
    pep_best = {"bootstrap_cap_offset": best_offs, "max_bias": best_bias}
    print(f"  Osm overrides: {osm_best}")
    print(f"  Pep overrides: {pep_best}")
    g, t, pd = run_config("combined", osm_overrides=osm_best, pep_overrides=pep_best)
    delta = g - baseline
    print(f"\n  COMBINED: Osm={t['ASH_COATED_OSMIUM']:+.0f}  Pep={t['INTARIAN_PEPPER_ROOT']:+.0f}  TOTAL={g:+.0f}  delta={delta:+.0f}")
    print(f"  day-1={sum(pd[-1].values()):+.0f}  day0={sum(pd[0].values()):+.0f}  day+1={sum(pd[1].values()):+.0f}")

    print(f"\n[SUMMARY] Baseline={baseline:+.0f}  Best combined={g:+.0f}  Gain={delta:+.0f}")


if __name__ == "__main__":
    main()
