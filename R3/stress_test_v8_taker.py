"""
v8-taker : IV smile en TAKER UNIQUEMENT.
Principe : pas de MM passive (évite adverse selection qui coulait v7).
On prend les mispricings quand |market - smile_FV| > threshold.

Test 1-strike-at-a-time sous S1 opt / S2 real / S3 pess.
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


def run(configs, haircut, after_queue):
    """configs = list of (strike, position_limit, taker_threshold, taker_max_clip)
    None = baseline v6."""
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = haircut
    _AFTER_QUEUE = after_queue
    reset()
    if configs:
        for (strike, plimit, th, clip) in configs:
            sym = f"VEV_{strike}"
            PP[sym]["position_limit"] = plimit
            PP[sym]["use_smile_taker"] = True
            PP[sym]["taker_threshold"] = th
            PP[sym]["taker_max_clip"] = clip
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


print("=" * 100, flush=True)
print("v8-TAKER : IV smile en taker uniquement, 1 strike à la fois, 3 scénarios", flush=True)
print("=" * 100, flush=True)

# Baseline v6 sous les 3 scénarios
scenarios = [
    ("S1 opt (h=0%)",          0.0,  False),
    ("S2 real (h=25%, queue)", 0.25, True),
    ("S3 pess (h=50%, queue)", 0.50, True),
]

baselines = {}
for label, h, aq in scenarios:
    tot, _ = run(None, h, aq)
    baselines[label] = tot
    print(f"  v6 baseline {label:<28s} TOTAL={tot:+.0f}", flush=True)
print(flush=True)

# Grille 1-strike
# Focus sur les strikes avec biais significatif : 5400 (-0.014), 6000 (+0.014), 6500, 5200, 5300, 5500
# Et 4500 (+0.049 massif mais déjà actif en MM, on teste si le taker ADD)
strikes = [5400, 6000, 5200, 5300, 5500, 6500]
thresholds = [2.0, 3.0, 5.0]  # plus threshold grand = moins de trades, mais plus edge par trade
clips = [10, 30, 100]
plimit = 100

print("-" * 100, flush=True)
print(f"{'config':<35s}  " + "  ".join(f"{s[0]:>12s}" for s in scenarios) +
      f"  {'min3':>10s}  {'Δmin':>10s}", flush=True)
print("-" * 100, flush=True)

results = []
for strike in strikes:
    for th in thresholds:
        for clip in clips:
            label = f"VEV_{strike} L={plimit} th={th} clip={clip}"
            row = {}
            for s_label, h, aq in scenarios:
                total, by_prod = run([(strike, plimit, th, clip)], h, aq)
                row[s_label] = total
            min3 = min(row.values())
            base_min = min(baselines.values())
            delta = min3 - base_min
            results.append((strike, th, clip, row, min3, delta))
            line = f"{label:<35s}  " + "  ".join(f"{row[s[0]]:>+12.0f}" for s in scenarios)
            line += f"  {min3:>+10.0f}  {delta:>+10.0f}"
            print(line, flush=True)
    print("-" * 100, flush=True)

# TOP 5
print(flush=True)
print("=" * 100, flush=True)
print("TOP 5 Δmin3 vs v6 baseline (S3 pess dominant) :", flush=True)
top = sorted(results, key=lambda r: -r[5])[:5]
for strike, th, clip, row, min3, delta in top:
    row_str = "  ".join(f"{row[s[0]]:>+9.0f}" for s in scenarios)
    print(f"  VEV_{strike} th={th} clip={clip}  {row_str}  Δmin={delta:+.0f}", flush=True)

print(flush=True)
print("=" * 100, flush=True)
print("DÉCISION :", flush=True)
print("  Δmin3 > +5k  → candidat submit (activer ce strike + config en taker)", flush=True)
print("  Δmin3 > +15k → STRONG submit (alpha robuste sous stress)", flush=True)
print("  Δmin3 ≤ 0    → rester v6", flush=True)
