"""
v7-clean : isolation propre, un strike à la fois, baseline v6 vraie.
Pas d'import de stress_test_v7 (évite mutation PP au chargement).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
# Snapshot PROPRE de la config v6 (état initial du trader)
BASE_PP = {k: dict(v) for k, v in PP.items()}

_RAW_APPLY = lb.apply_passive_fills
_HAIRCUT = 0.25
_AFTER_QUEUE = True


def _patched_apply_passive_fills(passive_orders, trades_this_tick, depth_prev,
                                 positions, cash, product, limit):
    if not passive_orders or not trades_this_tick:
        return
    our_buys, our_sells = {}, {}
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
            if [p for p in our_sells if p <= tp and our_sells[p] > 0]:
                is_buy_candidate = True
            elif [p for p in our_buys if p >= tp and our_buys[p] > 0]:
                is_sell_candidate = True

        if is_buy_candidate:
            remaining_tv = tv
            for p in sorted(our_sells.keys()):
                if remaining_tv <= 0 or p > tp:
                    break
                our_qty = our_sells[p]
                if our_qty <= 0:
                    continue
                if book_ba is None or p < book_ba:
                    fill = min(our_qty, remaining_tv)
                    if _HAIRCUT > 0:
                        fill = int(round(fill * (1.0 - _HAIRCUT)))
                else:
                    if _AFTER_QUEUE:
                        fill = 0
                    else:
                        book_at_p = -depth_prev.sell_orders.get(p, 0) if depth_prev else 0
                        total = our_qty + book_at_p
                        fill = min(our_qty, int(round(remaining_tv * our_qty / total))) if total > 0 else 0
                        if _HAIRCUT > 0:
                            fill = int(round(fill * (1.0 - _HAIRCUT)))
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
                if remaining_tv <= 0 or p < tp:
                    break
                our_qty = our_buys[p]
                if our_qty <= 0:
                    continue
                if book_bb is None or p > book_bb:
                    fill = min(our_qty, remaining_tv)
                    if _HAIRCUT > 0:
                        fill = int(round(fill * (1.0 - _HAIRCUT)))
                else:
                    if _AFTER_QUEUE:
                        fill = 0
                    else:
                        book_at_p = depth_prev.buy_orders.get(p, 0) if depth_prev else 0
                        total = our_qty + book_at_p
                        fill = min(our_qty, int(round(remaining_tv * our_qty / total))) if total > 0 else 0
                        if _HAIRCUT > 0:
                            fill = int(round(fill * (1.0 - _HAIRCUT)))
                room = limit - positions[product]
                fill = min(fill, room)
                if fill > 0:
                    positions[product] += fill
                    cash[product] -= fill * p
                    our_buys[p] = our_qty - fill
                    remaining_tv -= fill


def reset():
    PP.clear()
    for k, v in BASE_PP.items():
        PP[k] = dict(v)


def run(strike, limit, edge):
    reset()
    if strike is not None:
        sym = f"VEV_{strike}"
        PP[sym]["position_limit"] = limit
        PP[sym]["use_smile_fv"] = True
        PP[sym]["make_edge"] = edge
        PP[sym]["inventory_clearing"] = True
        PP[sym]["clearing_threshold"] = 0.30
        PP[sym]["min_wall_volume"] = 3
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        total = 0
        by_prod = {}
        for d in (0, 1, 2):
            pnl = simulate(d)
            total += sum(pnl.values())
            for k, v in pnl.items():
                by_prod[k] = by_prod.get(k, 0) + v
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return total, by_prod


print("=" * 90, flush=True)
print("v7-CLEAN : baseline v6 propre, 1 strike à la fois (S2 real h=25%, queue)", flush=True)
print("=" * 90, flush=True)

total_base, by_prod_base = run(None, 0, 0)
print(f"  v6 TRUE baseline                TOTAL={total_base:+.0f}", flush=True)
print(flush=True)

configs = [
    (5400, 30, 3),
    (5400, 30, 5),
    (5400, 50, 3),
    (5400, 100, 3),
    (5200, 50, 3),
    (5200, 100, 3),
    (5300, 50, 3),
    (5300, 100, 3),
    (5500, 50, 3),
    (6000, 50, 3),
    (6500, 50, 3),
]

results = []
for (strike, limit, edge) in configs:
    total, by_prod = run(strike, limit, edge)
    delta = total - total_base
    vev_delta = by_prod.get(f"VEV_{strike}", 0) - by_prod_base.get(f"VEV_{strike}", 0)
    print(f"  VEV_{strike} L={limit:>3d} E={edge}  TOTAL={total:+.0f}  "
          f"Δvs_v6={delta:+.0f}  ΔVEV_{strike}={vev_delta:+.0f}", flush=True)
    results.append((strike, limit, edge, total, delta, vev_delta))

print(flush=True)
print("=" * 90, flush=True)
print("TOP 5 gains vs v6 baseline :", flush=True)
top = sorted(results, key=lambda r: -r[4])[:5]
for strike, limit, edge, total, delta, vev_delta in top:
    print(f"  VEV_{strike} L={limit} E={edge}  Δ={delta:+.0f}", flush=True)

print(flush=True)
print("Si Top-1 gain > +5k → reco aggro : activer ce strike dans trader", flush=True)
print("Si Top-1 gain négatif → pas de resubmit, rester v6", flush=True)
