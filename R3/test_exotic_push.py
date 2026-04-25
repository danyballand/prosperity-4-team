"""
Tests exotiques :
- Cross-product : signal HYD anon → push VEV ITM (replication delta)
- VEV ITM en TAKER (pas MM) sur mispricing vs synthétique
- HYD double regime : SHORT_LITE multi-niveau + extension WAIT
- Aggressive VE : skew + dual edge maker
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
    trader_r3.trade_product = _RAW_TRADE


def run(modifier_fn, label):
    reset()
    if modifier_fn: modifier_fn()
    pnl_j2 = simulate(2, max_ts=100_000)
    j2 = sum(pnl_j2.values())
    h = pnl_j2.get('HYDROGEL_PACK', 0)
    v = pnl_j2.get('VELVETFRUIT_EXTRACT', 0)
    vev_itm = sum(pnl_j2.get(f'VEV_{s}', 0) for s in [4000, 4500, 5000, 5100])
    t3d = sum(sum(simulate(d).values()) for d in (0,1,2))
    print(f'{label:<55s}  j2={j2:+.0f}  3d={t3d:+.0f}  HYD={h:+.0f}  VE={v:+.0f}  ITM={vev_itm:+.0f}', flush=True)


print('=' * 130, flush=True)
print('PUSH EXOTIC — cross-product et combos avancés', flush=True)
print('=' * 130, flush=True)

run(None, 'v17 baseline')
print(flush=True)

# === I. HYD make_edge réduction conditionnelle ===
print('--- I. HYD make_edge réduit ET regime_size up ---', flush=True)
def hyd_combo(edge, sz):
    def f():
        PP['HYDROGEL_PACK']['make_edge'] = edge
        PP['HYDROGEL_PACK']['hyd_short_lite_size'] = sz
    return f
for e, s in [(15, 100), (20, 100), (15, 150), (10, 100)]:
    run(hyd_combo(e, s), f'I. HYD edge={e} sz={s}')
print(flush=True)

# === J. VE skew agressif + clear ===
print('--- J. VE aggressive ---', flush=True)
def ve_aggro(skew, clear, edge):
    def f():
        PP['VELVETFRUIT_EXTRACT']['skew_ticks_per_unit'] = skew
        PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = clear
        PP['VELVETFRUIT_EXTRACT']['make_edge'] = edge
    return f
for sk, cl, e in [(0.05, True, 2), (0.08, True, 2), (0.05, True, 1), (0.1, True, 3)]:
    run(ve_aggro(sk, cl, e), f'J. VE skew={sk} clear={cl} edge={e}')
print(flush=True)

# === K. VEV ITM TAKER mode sur synthetique mispricing ===
# VEV_4000 prix theorique = max(VE - 4000, 0). Si VEV_4000 < VE-4000 → BUY VEV (cheap)
print('--- K. VEV ITM synthetic taker (acheter quand VEV < VE-K) ---', flush=True)
def synth_taker(target_strikes, threshold):
    def patched(product, state, trader_data):
        if product not in [f'VEV_{s}' for s in target_strikes]:
            return _RAW_TRADE(product, state, trader_data)
        depth = state.order_depths.get(product)
        ve_depth = state.order_depths.get('VELVETFRUIT_EXTRACT')
        if not depth or not ve_depth or not depth.buy_orders or not depth.sell_orders or not ve_depth.buy_orders or not ve_depth.sell_orders:
            return _RAW_TRADE(product, state, trader_data)
        bb = max(depth.buy_orders.keys())
        ba = min(depth.sell_orders.keys())
        ve_mid = (max(ve_depth.buy_orders.keys()) + min(ve_depth.sell_orders.keys())) / 2.0
        strike = int(product.split('_')[1])
        synth = max(ve_mid - strike, 0)
        position = state.position.get(product, 0)
        limit = int(PP[product].get('position_limit', 300))
        orders = []
        if ba < synth - threshold:
            room = limit - position
            qty_avail = -depth.sell_orders.get(ba, 0)
            qty = min(room, qty_avail, 30)
            if qty > 0:
                orders.append(Order(product, ba, qty))
        elif bb > synth + threshold:
            room = limit + position
            qty_avail = depth.buy_orders.get(bb, 0)
            qty = min(room, qty_avail, 30)
            if qty > 0:
                orders.append(Order(product, bb, -qty))
        return orders
    return patched

def setup_synth(strikes, th):
    def f():
        trader_r3.trade_product = synth_taker(strikes, th)
    return f
for th in [1, 2, 3, 5]:
    run(setup_synth([4000, 4500], th), f'K. VEV 4000+4500 synth taker th={th}')
print(flush=True)

# === L. SHORT_LITE étendu à TOUS les regimes (jamais bloqué) ===
print('--- L. SHORT_LITE + LONG_LITE étendu (NB: nécessite mod code) — skip pour le moment ---', flush=True)
print(flush=True)

# === M. ULTIMATE COMBO ===
print('--- M. ULTIMATE COMBO ---', flush=True)
def ultimate():
    PP['HYDROGEL_PACK']['hyd_short_lite_size'] = 100
    PP['HYDROGEL_PACK']['make_edge'] = 15
    PP['VELVETFRUIT_EXTRACT']['skew_ticks_per_unit'] = 0.05
    PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = True
    for s in [4000, 4500]: PP[f'VEV_{s}']['make_edge'] = 2
    for s in [5000, 5100]: PP[f'VEV_{s}']['make_edge'] = 1
run(ultimate, 'M. ultimate (HYD + VE + VEV ITM penny)')

print('=' * 130, flush=True)
