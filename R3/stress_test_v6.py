"""
Stress-test v6 (v5 HYD + VE directional fix) vs v5 baseline.

v5 baseline : VE skew=0.05, inventory_clearing=True  → +139,420 S1 / +128,352 S3
v6 patch    : VE skew=0.0,  inventory_clearing=False → attendu +151,900 S1 / ~+140,300 S3

Teste les deux sous S1/S2/S3 pour confirmer gain robuste.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_HYD = dict(PP["HYDROGEL_PACK"])
BASE_VE  = dict(PP["VELVETFRUIT_EXTRACT"])

_RAW_APPLY = lb.apply_passive_fills
_HAIRCUT = 0.0
_AFTER_QUEUE = False


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


def set_ve(**kwargs):
    PP["VELVETFRUIT_EXTRACT"].clear()
    PP["VELVETFRUIT_EXTRACT"].update(BASE_VE)
    for k, v in kwargs.items():
        PP["VELVETFRUIT_EXTRACT"][k] = v


def run_config(label, ve_override, haircut, after_queue):
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = haircut
    _AFTER_QUEUE = after_queue
    set_ve(**ve_override)
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        total_all = 0
        total_ve = 0
        total_hyd = 0
        total_vev = 0
        d2_100k_total = 0
        d2_100k_hyd = 0
        for d in (0, 1, 2):
            pnl = simulate(d)
            total_all += sum(pnl.values())
            total_ve += pnl.get("VELVETFRUIT_EXTRACT", 0)
            total_hyd += pnl.get("HYDROGEL_PACK", 0)
            total_vev += sum(v for k, v in pnl.items() if k.startswith("VEV_"))
        pnl_100 = simulate(2, max_ts=100_000)
        d2_100k_total = sum(pnl_100.values())
        d2_100k_hyd = pnl_100.get("HYDROGEL_PACK", 0)
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return total_all, total_hyd, total_ve, total_vev, d2_100k_total, d2_100k_hyd


# v5 (original) : skew=0.05, clearing=True
V5_VE = dict(skew_ticks_per_unit=0.05, inventory_clearing=True)
# v6 (patch)    : skew=0.0, clearing=False
V6_VE = dict(skew_ticks_per_unit=0.0, inventory_clearing=False)

scenarios = [
    ("S1 opt (h=0%)",            0.0,  False),
    ("S2 real (h=25%, queue)",   0.25, True),
    ("S3 pess (h=50%, queue)",   0.50, True),
]

print("=" * 110, flush=True)
print("Stress-test v6 vs v5 baseline — 3 scenarios haircut", flush=True)
print("=" * 110, flush=True)
print(f"{'Scenario':<25s}  {'Config':<12s}  {'TOTAL':>8s}  {'HYD':>8s}  {'VE':>7s}  {'VEV':>6s}  {'d2_100k':>8s}  {'d2_HYD':>7s}", flush=True)
print("-" * 110, flush=True)

summary = {}
for s_label, haircut, after_q in scenarios:
    for v_label, ve_cfg in [("v5 baseline", V5_VE), ("v6 (VE fix)", V6_VE)]:
        total, hyd, ve, vev, d2_t, d2_h = run_config(v_label, ve_cfg, haircut, after_q)
        summary[(s_label, v_label)] = (total, hyd, ve, vev, d2_t, d2_h)
        print(f"{s_label:<25s}  {v_label:<12s}  {total:>+8.0f}  {hyd:>+8.0f}  {ve:>+7.0f}  {vev:>+6.0f}  {d2_t:>+8.0f}  {d2_h:>+7.0f}", flush=True)
    # Delta
    s5 = summary[(s_label, "v5 baseline")]
    s6 = summary[(s_label, "v6 (VE fix)")]
    print(f"{s_label:<25s}  {'Δ v6-v5':<12s}  {s6[0]-s5[0]:>+8.0f}  {s6[1]-s5[1]:>+8.0f}  {s6[2]-s5[2]:>+7.0f}  {s6[3]-s5[3]:>+6.0f}  {s6[4]-s5[4]:>+8.0f}  {s6[5]-s5[5]:>+7.0f}", flush=True)
    print("-" * 110, flush=True)

print()
print("=" * 110, flush=True)
print("DECISION MATRIX", flush=True)
print("=" * 110, flush=True)
print(f"{'Config':<14s}  " + "  ".join(f"{s[0]:>16s}" for s in scenarios) + f"  {'min 3d':>8s}  {'min d2_100k':>11s}", flush=True)
for v_label in ("v5 baseline", "v6 (VE fix)"):
    row = f"{v_label:<14s}  "
    mins = []
    mins_d2 = []
    for s_label, _, _ in scenarios:
        total, hyd, ve, vev, d2_t, d2_h = summary[(s_label, v_label)]
        mins.append(total)
        mins_d2.append(d2_t)
        row += f"{total:>+16.0f}  "
    row += f"{min(mins):>+8.0f}  {min(mins_d2):>+11.0f}"
    print(row, flush=True)

s5_min = min(summary[(s[0], "v5 baseline")][0] for s in scenarios)
s6_min = min(summary[(s[0], "v6 (VE fix)")][0] for s in scenarios)
print()
print("=" * 110, flush=True)
print(f"Verdict : v6 min PnL = {s6_min:+.0f}  vs  v5 min PnL = {s5_min:+.0f}  →  Δ worst-case = {s6_min-s5_min:+.0f}", flush=True)
print("=" * 110, flush=True)
