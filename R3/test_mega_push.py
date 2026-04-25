"""
MEGA-TEST : tester tous les axes pour pousser au-delà de v12 (+22,776 live).
Backtest jour2_100k + 3d sur chaque variation.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_PP = {k: dict(v) for k, v in PP.items()}


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
    t3d = sum(sum(simulate(d).values()) for d in (0,1,2))
    print(f'{label:<50s}  j2_100k={j2:+.0f}  3d={t3d:+.0f}  HYD={h:+.0f}  VE={v:+.0f}  VEV_ITM={vev_itm:+.0f}', flush=True)
    return j2, t3d


print('=' * 130, flush=True)
print('MEGA-TEST PUSH — toutes pistes pour battre v17 baseline', flush=True)
print('=' * 130, flush=True)

# Baseline v17
v17_j2, v17_3d = run(None, 'v17 baseline')
print(flush=True)

# === A. VEV ITM penny edge sweep ===
print('--- A. VEV ITM penny edge sweep (force edge=N sur 4000/4500/5000/5100) ---', flush=True)
def vev_itm_edge(e):
    def f():
        for s in [4000, 4500]: PP[f'VEV_{s}']['make_edge'] = e
        for s in [5000, 5100]: PP[f'VEV_{s}']['make_edge'] = max(1, e-2)
    return f
for e in [1, 2, 3, 4]:
    run(vev_itm_edge(e), f'A. VEV ITM edge=4500-{e}/5000-{max(1,e-2)}')
print(flush=True)

# === B. VE config alternatives ===
print('--- B. VE config (skew + inv_clearing) ---', flush=True)
def ve_config(skew, clear):
    def f():
        PP['VELVETFRUIT_EXTRACT']['skew_ticks_per_unit'] = skew
        PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = clear
    return f
for skew, clear in [(0.05, True), (0.05, False), (0.1, True), (0.0, True)]:
    run(ve_config(skew, clear), f'B. VE skew={skew} clear={clear}')
print(flush=True)

# === C. SHORT_LITE multi-level depth sweep ===
print('--- C. SHORT_LITE depth (top N bids) — necessite modif code mais on simule via size ---', flush=True)
# Le code actuel vend top 3. Tester direct via short_lite_size puisque nb levels = fixed
for sz in [30, 60, 100, 150, 200]:
    def setsz(s=sz):
        def f(): PP['HYDROGEL_PACK']['hyd_short_lite_size'] = s
        return f
    run(setsz(), f'C. SHORT_LITE size={sz}')
print(flush=True)

# === D. Combos top ===
print('--- D. COMBOS finaux ---', flush=True)
def combo_a():
    PP['HYDROGEL_PACK']['hyd_short_lite_size'] = 100
    for s in [4000, 4500]: PP[f'VEV_{s}']['make_edge'] = 2
    for s in [5000, 5100]: PP[f'VEV_{s}']['make_edge'] = 1
def combo_b():
    PP['HYDROGEL_PACK']['hyd_short_lite_size'] = 100
    PP['VELVETFRUIT_EXTRACT']['skew_ticks_per_unit'] = 0.05
    PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = True
def combo_c():
    PP['HYDROGEL_PACK']['hyd_short_lite_size'] = 100
    for s in [4000, 4500]: PP[f'VEV_{s}']['make_edge'] = 2
    PP['VELVETFRUIT_EXTRACT']['skew_ticks_per_unit'] = 0.05
    PP['VELVETFRUIT_EXTRACT']['inventory_clearing'] = True

for fn, label in [(combo_a, 'D. combo_a (HYD sz100 + VEV ITM edge=2/1)'),
                   (combo_b, 'D. combo_b (HYD sz100 + VE skew/clear)'),
                   (combo_c, 'D. combo_c (HYD sz100 + VEV edge=2 + VE skew/clear)')]:
    run(fn, label)

print(flush=True)
print('=' * 130, flush=True)
print(f'v17 baseline pour comparer : j2_100k={v17_j2:+.0f}  3d={v17_3d:+.0f}', flush=True)
print('Critère : j2_100k > v17 ET 3d > 100k → candidat live', flush=True)
print('=' * 130, flush=True)
