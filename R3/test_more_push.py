"""
Tests additionnels en parallèle :
- VEV OTM price-improve (bb+1)
- LONG_LITE avec restrictions strictes (cooldown, position cap)
- SHORT_LITE depth=5 niveaux
- HYD make_edge réduction quand regime NEUTRAL_MM
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate
from datamodel import Order

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}

import trader_r3
_RAW_TRADE = trader_r3.trade_product


def reset():
    PP.clear()
    for k, v in BASE_PP.items(): PP[k] = dict(v)


def run(modifier_fn, label):
    reset()
    if modifier_fn: modifier_fn()
    pnl_j2 = simulate(2, max_ts=100_000)
    j2 = sum(pnl_j2.values())
    h = pnl_j2.get('HYDROGEL_PACK', 0)
    v = pnl_j2.get('VELVETFRUIT_EXTRACT', 0)
    vev_itm = sum(pnl_j2.get(f'VEV_{s}', 0) for s in [4000, 4500, 5000, 5100])
    vev_otm = sum(pnl_j2.get(f'VEV_{s}', 0) for s in [5300, 5400, 5500, 6000, 6500])
    t3d = sum(sum(simulate(d).values()) for d in (0,1,2))
    print(f'{label:<50s}  j2={j2:+.0f}  3d={t3d:+.0f}  HYD={h:+.0f}  VE={v:+.0f}  ITM={vev_itm:+.0f}  OTM={vev_otm:+.0f}', flush=True)


print('=' * 130, flush=True)
print('PUSH ROUND 2 — pistes additionnelles', flush=True)
print('=' * 130, flush=True)

# Baseline v17
run(None, 'v17 baseline')
print(flush=True)

# === E. VEV OTM long-bid avec PRICE-IMPROVE (bb+1) au lieu de queue ===
print('--- E. VEV OTM 5400/5500 long-only avec price-improve bb+1 ---', flush=True)
def patched_otm_pi(target_strikes):
    def patched(product, state, trader_data):
        if product in [f'VEV_{s}' for s in target_strikes]:
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                return _RAW_TRADE(product, state, trader_data)
            bb = max(depth.buy_orders.keys())
            ba = min(depth.sell_orders.keys())
            position = state.position.get(product, 0)
            limit = int(PP[product].get('position_limit', 50))
            room = limit - position
            orders = []
            if ba - bb > 1 and room > 0:  # spread permet bb+1 < ba (non-crossing)
                bid_px = bb + 1
                qty = min(room, 10)
                if qty > 0:
                    orders.append(Order(product, bid_px, qty))
            return orders
        return _RAW_TRADE(product, state, trader_data)
    return patched

def setup_otm_pi(strikes, lim=50):
    def f():
        for s in strikes:
            PP[f'VEV_{s}']['position_limit'] = lim
        trader_r3.trade_product = patched_otm_pi(strikes)
    return f

# Need to reset trade_product
def cleanup_after():
    trader_r3.trade_product = _RAW_TRADE

run(setup_otm_pi([5400], 30), 'E. OTM 5400 only PI lim=30')
cleanup_after()
run(setup_otm_pi([5400, 5500], 30), 'E. OTM 5400+5500 PI lim=30')
cleanup_after()
run(setup_otm_pi([5400, 5500], 50), 'E. OTM 5400+5500 PI lim=50')
cleanup_after()
print(flush=True)

# === F. VE inventory_clearing variations ===
print('--- F. VE inv_clearing settings ---', flush=True)
def ve_clearing(thresh, urgent):
    def f():
        PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = True
        PP['VELVETFRUIT_EXTRACT']['clearing_threshold'] = thresh
        PP['VELVETFRUIT_EXTRACT']['clearing_urgent_fraction'] = urgent
    return f
for th, ur in [(0.10, 0.50), (0.20, 0.60), (0.30, 0.70), (0.50, 0.80)]:
    run(ve_clearing(th, ur), f'F. VE clear th={th} urg={ur}')
print(flush=True)

# === G. HYD make_edge plus fin (déjà testé via test_hyd_make_edge mais avec regime actuel) ===
print('--- G. HYD make_edge (avec regime ON) ---', flush=True)
def hyd_make(e):
    def f(): PP['HYDROGEL_PACK']['make_edge'] = e
    return f
for e in [97, 50, 30, 20, 15, 10]:
    run(hyd_make(e), f'G. HYD make_edge={e}')
print(flush=True)

# === H. VEV ITM make_edge=1 + bigger position_limit ===
print('--- H. VEV ITM penny + limit boost ---', flush=True)
def vev_itm_aggressive(edge_45, edge_50, lim):
    def f():
        for s in [4000, 4500]:
            PP[f'VEV_{s}']['make_edge'] = edge_45
            PP[f'VEV_{s}']['position_limit'] = lim
        for s in [5000, 5100]:
            PP[f'VEV_{s}']['make_edge'] = edge_50
            PP[f'VEV_{s}']['position_limit'] = lim
    return f
for e45, e50, lim in [(2, 1, 300), (3, 2, 300), (1, 1, 300)]:
    run(vev_itm_aggressive(e45, e50, lim), f'H. VEV ITM edge {e45}/{e50} lim={lim}')
print(flush=True)

print('=' * 130, flush=True)
print('Si une variante > v17 jour2 ET pas catastrophique 3d → candidat live', flush=True)
print('=' * 130, flush=True)
