"""
Test MULTI-STRIKE taker simultané.
v8 single-strike : VEV_5400 +563, VEV_5500 +269, VEV_5300 +30. Total potentiel +862.
Mais peuvent-ils s'ADDITIONNER ou bien interagir négativement (corrélation) ?
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}

_RAW_APPLY = lb.apply_passive_fills
_HAIRCUT = 0.25
_AFTER_QUEUE = True


def _patched_apply_passive_fills(passive_orders, trades_this_tick, depth_prev,
                                 positions, cash, product, limit):
    if not passive_orders or not trades_this_tick: return
    our_buys, our_sells = {}, {}
    for o in passive_orders:
        if o.quantity > 0:
            our_buys[o.price] = our_buys.get(o.price, 0) + o.quantity
        elif o.quantity < 0:
            our_sells[o.price] = our_sells.get(o.price, 0) + (-o.quantity)
    book_bb = max(depth_prev.buy_orders.keys()) if depth_prev and depth_prev.buy_orders else None
    book_ba = min(depth_prev.sell_orders.keys()) if depth_prev and depth_prev.sell_orders else None
    for tr in trades_this_tick:
        tp = tr.price; tv = abs(tr.quantity)
        if tv <= 0: continue
        is_buy_candidate = (book_ba is not None and tp >= book_ba)
        is_sell_candidate = (book_bb is not None and tp <= book_bb)
        if not is_buy_candidate and not is_sell_candidate:
            if [p for p in our_sells if p <= tp and our_sells[p] > 0]: is_buy_candidate = True
            elif [p for p in our_buys if p >= tp and our_buys[p] > 0]: is_sell_candidate = True
        if is_buy_candidate:
            remaining_tv = tv
            for p in sorted(our_sells.keys()):
                if remaining_tv <= 0 or p > tp: break
                our_qty = our_sells[p]
                if our_qty <= 0: continue
                if book_ba is None or p < book_ba:
                    fill = min(our_qty, remaining_tv)
                    if _HAIRCUT > 0: fill = int(round(fill * (1.0 - _HAIRCUT)))
                else:
                    fill = 0 if _AFTER_QUEUE else min(our_qty, remaining_tv)
                room = limit + positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] -= fill; cash[product] += fill * p
                    our_sells[p] = our_qty - fill; remaining_tv -= fill
        elif is_sell_candidate:
            remaining_tv = tv
            for p in sorted(our_buys.keys(), reverse=True):
                if remaining_tv <= 0 or p < tp: break
                our_qty = our_buys[p]
                if our_qty <= 0: continue
                if book_bb is None or p > book_bb:
                    fill = min(our_qty, remaining_tv)
                    if _HAIRCUT > 0: fill = int(round(fill * (1.0 - _HAIRCUT)))
                else:
                    fill = 0 if _AFTER_QUEUE else min(our_qty, remaining_tv)
                room = limit - positions[product]; fill = min(fill, room)
                if fill > 0:
                    positions[product] += fill; cash[product] -= fill * p
                    our_buys[p] = our_qty - fill; remaining_tv -= fill


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


def run(taker_strikes, h, aq):
    """taker_strikes : list of (strike, threshold, clip)."""
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = h; _AFTER_QUEUE = aq
    reset()
    for (strike, th, clip) in taker_strikes:
        sym = f"VEV_{strike}"
        PP[sym]["position_limit"] = 100
        PP[sym]["use_smile_taker"] = True
        PP[sym]["taker_threshold"] = th
        PP[sym]["taker_max_clip"] = clip
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        total = 0; by_prod = {}
        for d in (0, 1, 2):
            pnl = simulate(d)
            total += sum(pnl.values())
            for k, v in pnl.items(): by_prod[k] = by_prod.get(k, 0) + v
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return total, by_prod


configs = [
    ("v6 baseline",                       []),
    ("V5400 only",                        [(5400, 5.0, 30)]),
    ("V5500 only",                        [(5500, 2.0, 30)]),
    ("V5300 only",                        [(5300, 3.0, 30)]),
    ("V5400+V5500",                       [(5400, 5.0, 30), (5500, 2.0, 30)]),
    ("V5400+V5500+V5300",                 [(5400, 5.0, 30), (5500, 2.0, 30), (5300, 3.0, 30)]),
    ("V5400+V5500+V5300 (clip 100)",      [(5400, 5.0, 100), (5500, 2.0, 100), (5300, 3.0, 100)]),
    ("V5400+V5500+V5300 +V6000+V6500",    [(5400, 5.0, 30), (5500, 2.0, 30), (5300, 3.0, 30),
                                            (6000, 5.0, 30), (6500, 5.0, 30)]),
]

print("=" * 100, flush=True)
print("MULTI-STRIKE TAKER — recherche additivité (S2 real, h=25%, queue)", flush=True)
print("=" * 100, flush=True)

baseline_total = None
for label, strikes in configs:
    total, by_prod = run(strikes, 0.25, True)
    if baseline_total is None:
        baseline_total = total
        delta = 0
    else:
        delta = total - baseline_total
    vev_sum = sum(v for k, v in by_prod.items() if k.startswith("VEV_") and int(k.split("_")[1]) >= 5200)
    print(f"  {label:<40s}  TOTAL={total:>+9.0f}  Δ={delta:>+8.0f}  VEV_disabled_sum={vev_sum:+.0f}", flush=True)

print(flush=True)
print("Si Δ multi > Σ Δ single → additivité confirmée, on peut empiler", flush=True)
print("Si Δ multi < Σ Δ single → corrélation négative, choisir le best single", flush=True)
