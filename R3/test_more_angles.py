"""
Tests multiples angles non explorés :
1. VEV ITM (4000/4500) edge réduit SANS haircut (S1 opt) — l'audit pote dit +6.56 markout
2. OBI skew sur HYD (use_obi_skew déjà existe dans code)
3. Augmenter limit HYD au-delà de 200 ? (officiel = 200 mais voir effet)
4. Test informed_detection live mode sur HYD
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
_HAIRCUT = 0.0
_AFTER_QUEUE = False


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


def run_jour2(modifier_fn, h, aq):
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = h; _AFTER_QUEUE = aq
    reset()
    if modifier_fn: modifier_fn()
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        pnl = simulate(2, max_ts=100_000)
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return sum(pnl.values()), pnl


print("=" * 100, flush=True)
print("MORE ANGLES — VEV ITM no haircut, OBI HYD, limit HYD, informed HYD", flush=True)
print("=" * 100, flush=True)

# v9 baseline sans haircut (pour comparer apples-to-apples)
t_base_h0, p_base_h0 = run_jour2(None, 0.0, False)
print(f"v9 baseline jour2_100k S1 (h=0%) : TOTAL={t_base_h0:+.0f}", flush=True)
t_base_h25, p_base_h25 = run_jour2(None, 0.25, True)
print(f"v9 baseline jour2_100k S2 (h=25%): TOTAL={t_base_h25:+.0f}", flush=True)
print(flush=True)

# 1. VEV ITM edge=1/2 SANS haircut
print("--- VEV ITM edge réduit SANS haircut (S1 opt) ---", flush=True)
def mod_vev_itm(edge):
    def f():
        for s in [4000, 4500]: PP[f"VEV_{s}"]["make_edge"] = edge
        for s in [5000, 5100]: PP[f"VEV_{s}"]["make_edge"] = max(1, edge - 1)
    return f

for edge in [3, 2, 1]:
    t, p = run_jour2(mod_vev_itm(edge), 0.0, False)
    vev_itm = sum(p.get(f"VEV_{s}", 0) for s in [4000, 4500, 5000, 5100])
    delta = t - t_base_h0
    print(f"  VEV ITM edge={edge} (S1 h=0)  TOTAL={t:+.0f}  VEV_ITM={vev_itm:+.0f}  Δ={delta:+.0f}", flush=True)

# 2. OBI skew sur HYD (use_obi_skew=True)
print(flush=True)
print("--- OBI skew sur HYD ---", flush=True)
def mod_obi_hyd(strength):
    def f():
        PP["HYDROGEL_PACK"]["use_obi_skew"] = True
        PP["HYDROGEL_PACK"]["obi_strength"] = strength
    return f
for strength in [0.5, 1.0, 2.0, 3.0]:
    t, p = run_jour2(mod_obi_hyd(strength), 0.25, True)
    delta = t - t_base_h25
    print(f"  HYD obi_strength={strength}  TOTAL={t:+.0f}  HYD={p.get('HYDROGEL_PACK',0):+.0f}  Δ={delta:+.0f}", flush=True)

# 3. HYD limit > 200 (peut-être que +50 de marge donne plus de capture)
print(flush=True)
print("--- HYD position_limit > 200 ---", flush=True)
def mod_hyd_limit(lim):
    def f():
        PP["HYDROGEL_PACK"]["position_limit"] = lim
    return f
for lim in [100, 150, 200, 250, 300]:
    t, p = run_jour2(mod_hyd_limit(lim), 0.25, True)
    delta = t - t_base_h25
    print(f"  HYD limit={lim}  TOTAL={t:+.0f}  HYD={p.get('HYDROGEL_PACK',0):+.0f}  Δ={delta:+.0f}", flush=True)

# 4. Informed detection HYD live mode
print(flush=True)
print("--- HYD informed_detection live (id_markout) ---", flush=True)
def mod_informed_hyd():
    PP["HYDROGEL_PACK"]["id_markout"] = True
    PP["HYDROGEL_PACK"]["id_markout_horizon"] = 500
    PP["HYDROGEL_PACK"]["id_min_count"] = 4
    PP["HYDROGEL_PACK"]["id_min_mean"] = 2.0
    PP["HYDROGEL_PACK"]["id_min_tstat"] = 1.5
    PP["HYDROGEL_PACK"]["id_target"] = 60
t, p = run_jour2(mod_informed_hyd, 0.25, True)
delta = t - t_base_h25
print(f"  HYD informed_detection ON  TOTAL={t:+.0f}  HYD={p.get('HYDROGEL_PACK',0):+.0f}  Δ={delta:+.0f}", flush=True)
