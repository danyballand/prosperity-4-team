"""
Stress-test v7 (IV-smile FV) vs v6 baseline.

v6 baseline : 4 VEV strikes actifs (4000,4500,5000,5100), 6 disabled.
v7a : activer 6 strikes disabled avec use_smile_fv=True (gardé edge conservateur)
v7b : v7a + use_smile_fv sur 4500 (biggest biais +0.049)
v7c : v7b + use_smile_fv sur 5000/5100 aussi

Sous S1 opt / S2 real / S3 pess (haircut).
"""
import os, sys, copy
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
# Deep copy pour pouvoir reset
BASE_PP = {k: dict(v) for k, v in PP.items()}

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


def reset_pp():
    PP.clear()
    for k, v in BASE_PP.items():
        PP[k] = dict(v)


def config_v7(variant):
    """
    variant 'v6'  : baseline (aucune modif)
    variant 'v7a' : 6 strikes disabled (5200-6500) → activés avec smile FV
    variant 'v7b' : v7a + 4500 switched to smile FV
    variant 'v7c' : v7b + 5000/5100 switched to smile FV
    """
    reset_pp()
    if variant == "v6":
        return

    if variant in ("v7a", "v7b", "v7c"):
        # Activer les 6 strikes disabled avec smile FV + edge conservateur
        for s in (5200, 5300, 5400, 5500, 6000, 6500):
            sym = f"VEV_{s}"
            PP[sym]["position_limit"] = 100       # modéré (pas 300 full pour limiter risque)
            PP[sym]["use_smile_fv"] = True
            PP[sym]["make_edge"] = 2              # mince : smile FV est précis
            PP[sym]["inventory_clearing"] = True
            PP[sym]["clearing_threshold"] = 0.30
            PP[sym]["min_wall_volume"] = 3

    if variant in ("v7b", "v7c"):
        PP["VEV_4500"]["use_smile_fv"] = True
        PP["VEV_4500"]["make_edge"] = 3           # biais +0.049 dominant → edge fin OK

    if variant == "v7c":
        PP["VEV_5000"]["use_smile_fv"] = True
        PP["VEV_5100"]["use_smile_fv"] = True


def run_config(variant, haircut, after_queue):
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = haircut
    _AFTER_QUEUE = after_queue
    config_v7(variant)
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        total_all = 0
        by_prod = {}
        for d in (0, 1, 2):
            pnl = simulate(d)
            total_all += sum(pnl.values())
            for k, v in pnl.items():
                by_prod[k] = by_prod.get(k, 0) + v
        pnl_100 = simulate(2, max_ts=100_000)
        d2_100k = sum(pnl_100.values())
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return total_all, by_prod, d2_100k


scenarios = [
    ("S1 opt (h=0%)",           0.0,  False),
    ("S2 real (h=25%, queue)",  0.25, True),
    ("S3 pess (h=50%, queue)",  0.50, True),
]
variants = ["v6", "v7a", "v7b", "v7c"]

print("=" * 120, flush=True)
print("Stress-test v7 (IV smile FV) vs v6 baseline — 4 variants × 3 scenarios", flush=True)
print("=" * 120, flush=True)
print(f"{'Scenario':<24s}  {'Variant':<6s}  {'TOTAL':>8s}  {'HYD':>8s}  {'VE':>7s}  "
      f"{'VEV_new':>8s}  {'VEV_4500':>9s}  {'d2_100k':>8s}", flush=True)
print("-" * 120, flush=True)

summary = {}
for s_label, h, aq in scenarios:
    for v in variants:
        total, by_prod, d2_100k = run_config(v, h, aq)
        hyd = by_prod.get("HYDROGEL_PACK", 0)
        ve = by_prod.get("VELVETFRUIT_EXTRACT", 0)
        vev_new = sum(by_prod.get(f"VEV_{s}", 0) for s in (5200, 5300, 5400, 5500, 6000, 6500))
        vev_4500 = by_prod.get("VEV_4500", 0)
        summary[(s_label, v)] = (total, hyd, ve, vev_new, vev_4500, d2_100k)
        print(f"{s_label:<24s}  {v:<6s}  {total:>+8.0f}  {hyd:>+8.0f}  {ve:>+7.0f}  "
              f"{vev_new:>+8.0f}  {vev_4500:>+9.0f}  {d2_100k:>+8.0f}", flush=True)
    # Deltas
    base = summary[(s_label, "v6")][0]
    for v in ("v7a", "v7b", "v7c"):
        delta = summary[(s_label, v)][0] - base
        print(f"{'':<24s}  Δ{v:<5s}  {delta:>+8.0f}", flush=True)
    print("-" * 120, flush=True)

print()
print("=" * 120, flush=True)
print("DECISION MATRIX", flush=True)
print("=" * 120, flush=True)
print(f"{'Variant':<8s}  {'S1 opt':>12s}  {'S2 real':>12s}  {'S3 pess':>12s}  "
      f"{'min 3d':>10s}  {'Δ vs v6 (min)':>14s}", flush=True)
for v in variants:
    mins = [summary[(s[0], v)][0] for s in scenarios]
    min3 = min(mins)
    base_min = min(summary[(s[0], "v6")][0] for s in scenarios)
    delta = min3 - base_min
    row = f"{v:<8s}  " + "  ".join(f"{summary[(s[0], v)][0]:>+12.0f}" for s in scenarios)
    row += f"  {min3:>+10.0f}  {delta:>+14.0f}"
    print(row, flush=True)

print()
print("Décision :")
print("  Si best v7* min 3d > v6 min 3d de +5k → submit v7")
print("  Sinon → rester sur v6 (378162)")
