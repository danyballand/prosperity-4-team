"""
VEV_4500 a le plus gros biais smile (+0.049 = massivement sur-évalué). Il est DÉJÀ
en MM actif (limit=300, edge=5). On ajoute une COUCHE TAKER en plus du MM existant
pour capter le mispricing massif que le MM n'arbitre pas.

Idée : MM continue à quote, mais on ajoute des hits agressifs quand best_bid est
au-dessus du smile_FV (vendre cher) ou best_ask en dessous (acheter pas cher).

Modif technique : pour 4500, on PERMET use_smile_taker=True ET on garde MM (pas
d'early-return). Donc on patch trader_r3 temporairement pour ce test.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate
from datamodel import Order
try:
    from iv_quoter import compute_smile_fv
    OK = True
except: OK = False

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}

# Override trade_product pour ajouter taker overlay sur 4500 sans early-return
_RAW_TRADE = tm.trade_product
_TAKER_OVERLAY_STRIKE = None
_TAKER_OVERLAY_TH = 5.0
_TAKER_OVERLAY_CLIP = 30


def _trade_product_with_overlay(product, state, trader_data):
    orders = _RAW_TRADE(product, state, trader_data)
    if (_TAKER_OVERLAY_STRIKE is None or product != f"VEV_{_TAKER_OVERLAY_STRIKE}"
            or not OK):
        return orders
    depth = state.order_depths.get(product)
    if depth is None: return orders
    try:
        smile_fv = compute_smile_fv(state, _TAKER_OVERLAY_STRIKE)
    except: smile_fv = None
    if smile_fv is None: return orders
    pos = state.position.get(product, 0)
    limit = int(PP[product].get("position_limit", 0))
    bb = max(depth.buy_orders.keys()) if depth.buy_orders else None
    ba = min(depth.sell_orders.keys()) if depth.sell_orders else None
    # BUY si ba < smile - th
    if ba is not None and ba < smile_fv - _TAKER_OVERLAY_TH:
        room = limit - pos
        if room > 0:
            qty_avail = -depth.sell_orders.get(ba, 0)
            qty = min(qty_avail, room, _TAKER_OVERLAY_CLIP)
            if qty > 0: orders.append(Order(product, ba, qty))
    if bb is not None and bb > smile_fv + _TAKER_OVERLAY_TH:
        room = limit + pos
        if room > 0:
            qty_avail = depth.buy_orders.get(bb, 0)
            qty = min(qty_avail, room, _TAKER_OVERLAY_CLIP)
            if qty > 0: orders.append(Order(product, bb, -qty))
    return orders


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


def run(strike, th, clip):
    global _TAKER_OVERLAY_STRIKE, _TAKER_OVERLAY_TH, _TAKER_OVERLAY_CLIP
    _TAKER_OVERLAY_STRIKE = strike
    _TAKER_OVERLAY_TH = th
    _TAKER_OVERLAY_CLIP = clip
    reset()
    if strike is not None:
        tm.trade_product = _trade_product_with_overlay
    else:
        tm.trade_product = _RAW_TRADE
    try:
        total = 0; by_prod = {}
        for d in (0, 1, 2):
            pnl = simulate(d)
            total += sum(pnl.values())
            for k, v in pnl.items(): by_prod[k] = by_prod.get(k, 0) + v
    finally:
        tm.trade_product = _RAW_TRADE
    return total, by_prod


print("=" * 90, flush=True)
print("VEV_4500 TAKER OVERLAY (en plus du MM existant)", flush=True)
print("=" * 90, flush=True)

# Baseline
total_base, by_prod_base = run(None, 0, 0)
print(f"  v6 baseline                    TOTAL={total_base:+.0f}  VEV_4500={by_prod_base.get('VEV_4500',0):+.0f}", flush=True)

configs = [
    (4500, 3.0, 30),
    (4500, 5.0, 30),
    (4500, 8.0, 30),
    (4500, 10.0, 30),
    (4500, 5.0, 100),
    (4500, 5.0, 300),
    # Aussi tester sur 4000 (deep ITM, biais inconnu)
    (4000, 5.0, 30),
    (4000, 10.0, 30),
    # Et 5000/5100 ATM (les actifs)
    (5000, 5.0, 30),
    (5100, 5.0, 30),
]

for strike, th, clip in configs:
    total, by_prod = run(strike, th, clip)
    delta = total - total_base
    vev_delta = by_prod.get(f"VEV_{strike}", 0) - by_prod_base.get(f"VEV_{strike}", 0)
    print(f"  V{strike} overlay th={th} clip={clip}  TOTAL={total:+.0f}  Δ={delta:+.0f}  ΔV{strike}={vev_delta:+.0f}", flush=True)

print(flush=True)
print("Si Δ > +5k → overlay validé, code dans trader_r3 et submit", flush=True)
