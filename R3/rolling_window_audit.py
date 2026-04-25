"""
Rolling-window audit : pour chaque jour, capture la PnL curve mark-to-market
puis calcule le WORST DRAWDOWN sur fenêtres glissantes [10k, 25k, 50k, 100k, 200k].

Objectif : valider que v6 ne s'effondre pas sur une fenêtre courte adverse
(le submit live R3 est sur 0-100k seulement).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from collections import defaultdict
import local_backtest_r3 as lb
from local_backtest_r3 import (Trader, OrderDepth, Order, Listing, TradingState,
                                load_prices, load_trades, apply_passive_fills,
                                fill_crossing, _limit_for, PRODUCTS, LIVE_DURATION_TS)
import trader_r3 as tm

PP = tm.PRODUCT_PARAMS

# Snapshot baseline (v6 actuel)
BASE_PP = {k: dict(v) for k, v in PP.items()}


def simulate_curve(day, max_ts=LIVE_DURATION_TS):
    """Variante de simulate() qui enregistre la PnL mark-to-market à chaque tick.
    Retourne (timestamps, total_pnl_curve, by_prod_curves)."""
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
        except Exception as e:
            prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}
            continue

        for product, orders in result.items():
            depth = depths.get(product)
            if depth is None:
                continue
            limit = _limit_for(product)
            dm = OrderDepth()
            dm.buy_orders = dict(depth.buy_orders)
            dm.sell_orders = dict(depth.sell_orders)
            passive_orders_this_product = []
            for order in orders:
                remaining = fill_crossing(order, dm, positions, cash, product, limit)
                if remaining != 0:
                    passive_orders_this_product.append(Order(order.symbol, order.price, remaining))
            pending_passive[product] = passive_orders_this_product
            pending_depth[product] = dm
        prev_market_trades = {p: trades_by_ts.get(ts, {}).get(p, []) for p in PRODUCTS}

        # Mark-to-market
        total = 0.0
        for p in PRODUCTS:
            depth = depths.get(p)
            if depth and depth.buy_orders and depth.sell_orders:
                mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
            elif depth and depth.buy_orders:
                mid = max(depth.buy_orders)
            elif depth and depth.sell_orders:
                mid = min(depth.sell_orders)
            else:
                mid = 0.0
            pp = cash[p] + positions[p] * mid
            by_prod_curve[p].append(pp)
            total += pp
        pnl_curve.append(total)
        ts_curve.append(ts)

    return ts_curve, pnl_curve, by_prod_curve


def rolling_worst(curve, ts_curve, window_ts):
    """Pour chaque fenêtre de taille window_ts, calcule le pire drawdown
    PnL[t_end] - PnL[t_start]. Retourne (worst_delta, t_start, t_end)."""
    n = len(ts_curve)
    if n < 2:
        return 0.0, 0, 0
    worst = 0.0
    worst_start = worst_end = 0
    j = 0
    for i in range(n):
        # avancer j tant que ts_curve[j] - ts_curve[i] < window_ts
        while j < n and ts_curve[j] - ts_curve[i] < window_ts:
            j += 1
        # j pointe sur premier ts > t_i + window_ts
        if j > i + 1:
            end = j - 1 if j - 1 > i else i + 1
            if end >= n:
                continue
            delta = curve[end] - curve[i]
            if delta < worst:
                worst = delta
                worst_start = ts_curve[i]
                worst_end = ts_curve[end]
    return worst, worst_start, worst_end


def per_product_rolling(by_prod, ts_curve, window_ts):
    """Worst rolling delta par produit."""
    out = {}
    for p, curve in by_prod.items():
        w, _, _ = rolling_worst(curve, ts_curve, window_ts)
        out[p] = w
    return out


print("=" * 110, flush=True)
print("ROLLING WINDOW AUDIT — v6 sur 3 jours, fenêtres [10k, 25k, 50k, 100k, 200k]", flush=True)
print("=" * 110, flush=True)

windows = [10_000, 25_000, 50_000, 100_000, 200_000]

# Capture curves pour chaque jour
all_curves = {}
all_final = {}
for d in (0, 1, 2):
    print(f"\n--- Jour {d} ---", flush=True)
    ts_curve, pnl_curve, by_prod = simulate_curve(d, max_ts=1_000_000)
    all_curves[d] = (ts_curve, pnl_curve, by_prod)
    final = pnl_curve[-1] if pnl_curve else 0
    all_final[d] = final
    print(f"  PnL final 1M  : {final:+.0f}", flush=True)

    for W in windows:
        worst, t_start, t_end = rolling_worst(pnl_curve, ts_curve, W)
        # Top 3 produits worst contributors sur cette fenêtre
        per_p = per_product_rolling(by_prod, ts_curve, W)
        worst_p = sorted(per_p.items(), key=lambda x: x[1])[:3]
        worst_p_str = "  ".join(f"{lb._short(p)}:{v:+.0f}" for p, v in worst_p if v < 0)
        print(f"  W={W:>7d}  worst={worst:>+10.0f}  "
              f"[ts {t_start:>6d}→{t_end:>6d}]  worst_prods: {worst_p_str}", flush=True)

print()
print("=" * 110, flush=True)
print("RÉCAP — worst par taille de fenêtre, agrégé sur 3 jours", flush=True)
print("=" * 110, flush=True)
print(f"{'Window':>10s}  {'D0 worst':>12s}  {'D1 worst':>12s}  {'D2 worst':>12s}  {'WORST 3d':>12s}", flush=True)
for W in windows:
    worsts = []
    for d in (0, 1, 2):
        ts_curve, pnl_curve, _ = all_curves[d]
        w, _, _ = rolling_worst(pnl_curve, ts_curve, W)
        worsts.append(w)
    worst3 = min(worsts)
    print(f"{W:>10d}  " + "  ".join(f"{w:>+12.0f}" for w in worsts) + f"  {worst3:>+12.0f}", flush=True)

print()
print("FINAL PnL 1M par jour :", flush=True)
for d in (0, 1, 2):
    print(f"  Jour {d} : {all_final[d]:+.0f}", flush=True)
print(f"  TOTAL 3d : {sum(all_final.values()):+.0f}", flush=True)

print()
print("=" * 110, flush=True)
print("INTERPRÉTATION :", flush=True)
print("  Le submit live R3 est sur fenêtre 100k. Si worst W=100k > -10k → safe.", flush=True)
print("  Si worst W=25k ou W=50k catastrophique (< -15k) sur 1 jour → patch HYD requis.", flush=True)
print("=" * 110, flush=True)
