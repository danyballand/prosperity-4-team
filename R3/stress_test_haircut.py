"""
STRESS TEST v2 — reproduit l'audit de Codex (Gemini Deep Think + revue).

Modèle pessimiste "after_queue" + haircut passif :
  - Si notre prix == best bid/ask du book, on est DERRIÈRE la queue → 0 fill (au lieu du pro-rata optimiste).
  - Si notre prix est STRICTEMENT mieux que le book, fill "capped haircut" : qty × (1 - haircut).
  - haircut ∈ {0, 0.25, 0.50, 0.75} simule queue concurrente + latence live.

Objectif (fonction de score) :
  score = total_pnl
          - 2 * max(0, -worst_rolling_100k_total)  (pénalité grosse sur drawdown)
          - 0.5 * max(0, -worst_rolling_100k_hyd)

Le but : ne plus juger une config sur son PnL 3j full, mais sur sa survie aux fenêtres courtes adverses.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_HYD = dict(PP["HYDROGEL_PACK"])

_RAW_APPLY = lb.apply_passive_fills
_HAIRCUT = 0.0
_AFTER_QUEUE = False  # pessimistic : no fill at same price as book


def _patched_apply_passive_fills(passive_orders, trades_this_tick, depth_prev,
                                 positions, cash, product, limit):
    if not passive_orders or not trades_this_tick:
        return
    our_buys = {}
    our_sells = {}
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
                    # STRICTEMENT mieux que book : fill (avec haircut)
                    fill = min(our_qty, remaining_tv)
                    if _HAIRCUT > 0:
                        fill = int(round(fill * (1.0 - _HAIRCUT)))
                else:
                    # Même prix que book
                    if _AFTER_QUEUE:
                        fill = 0  # derrière la queue
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


def set_hyd(**kwargs):
    PP["HYDROGEL_PACK"].clear()
    PP["HYDROGEL_PACK"].update(BASE_HYD)
    for k, v in kwargs.items():
        PP["HYDROGEL_PACK"][k] = v


def bt_with_model(haircut, after_queue, max_ts=None):
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = haircut
    _AFTER_QUEUE = after_queue
    lb.apply_passive_fills = _patched_apply_passive_fills
    try:
        per_day_total = {}
        per_day_hyd = {}
        for d in (0, 1, 2):
            pnl = simulate(d) if max_ts is None else simulate(d, max_ts=max_ts)
            per_day_total[d] = sum(pnl.values())
            per_day_hyd[d] = pnl.get("HYDROGEL_PACK", 0.0)
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return per_day_total, per_day_hyd


def rolling_100k_worst(haircut, after_queue):
    """Pire fenêtre 100k rolling sur les 3 jours (10 windows × 3 days = 30 fenêtres)."""
    global _HAIRCUT, _AFTER_QUEUE
    _HAIRCUT = haircut
    _AFTER_QUEUE = after_queue
    lb.apply_passive_fills = _patched_apply_passive_fills
    worst_total = 1e9
    worst_hyd = 1e9
    try:
        for d in (0, 1, 2):
            prev_t, prev_h = 0.0, 0.0
            for cap in (100_000, 200_000, 300_000, 400_000, 500_000,
                        600_000, 700_000, 800_000, 900_000, 1_000_000):
                pnl = simulate(d, max_ts=cap)
                t = sum(pnl.values())
                h = pnl.get("HYDROGEL_PACK", 0.0)
                win_t = t - prev_t
                win_h = h - prev_h
                prev_t, prev_h = t, h
                if win_t < worst_total:
                    worst_total = win_t
                if win_h < worst_hyd:
                    worst_hyd = win_h
    finally:
        lb.apply_passive_fills = _RAW_APPLY
    return worst_total, worst_hyd


# ====================  CONFIGURATIONS À TESTER  ====================
CONFIGS = [
    ("v4 clip=10 tw=0",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50,
          fixed_fv_book_clip=10.0, make_edge=97, take_width=0, position_limit=200)),
    ("v5 clip=50 tw=2",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50,
          fixed_fv_book_clip=50.0, make_edge=97, take_width=2, position_limit=200)),
    ("v5_notake (disable_take)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50,
          fixed_fv_book_clip=50.0, make_edge=97, take_width=2, position_limit=200,
          disable_take=True)),
    ("v5_notake_noclear",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50,
          fixed_fv_book_clip=50.0, make_edge=97, take_width=2, position_limit=200,
          disable_take=True, inventory_clearing=False)),
    ("v6 dyn wall_mid lim=200 disable_take",
     dict(fixed_fv=None, use_microprice=True, make_edge=5, take_width=0,
          position_limit=200, disable_take=True)),
    ("v7 dyn wall_mid edge=3 lim=100 disable_take",
     dict(fixed_fv=None, use_microprice=True, make_edge=3, take_width=0,
          position_limit=100, disable_take=True)),
    ("v8 dyn wall_mid edge=5 lim=100 disable_take +noclear",
     dict(fixed_fv=None, use_microprice=True, make_edge=5, take_width=0,
          position_limit=100, disable_take=True, inventory_clearing=False)),
]


def run_scenario(scenario_label, haircut, after_queue):
    print("=" * 110)
    print(f"{scenario_label}  haircut={haircut:.0%}  after_queue={after_queue}")
    print("=" * 110)
    print(f"{'Config':<45s}  {'total':>8s}  {'HYD':>8s}  {'worst100k':>10s}  {'worstHYD':>9s}  {'score':>8s}")
    print("-" * 110)
    results = []
    for label, cfg in CONFIGS:
        set_hyd(**cfg)
        pdt, pdh = bt_with_model(haircut, after_queue)
        total_3d = sum(pdt.values())
        hyd_3d = sum(pdh.values())
        set_hyd(**cfg)
        worst_t, worst_h = rolling_100k_worst(haircut, after_queue)
        # score = total - 2*max(0,-worst_total) - 0.5*max(0,-worst_hyd)
        penalty = 2.0 * max(0, -worst_t) + 0.5 * max(0, -worst_h)
        score = total_3d - penalty
        print(f"{label:<45s}  {total_3d:>+8.0f}  {hyd_3d:>+8.0f}  {worst_t:>+10.0f}  {worst_h:>+9.0f}  {score:>+8.0f}")
        results.append((label, total_3d, hyd_3d, worst_t, worst_h, score))
    print()
    best = max(results, key=lambda r: r[5])
    print(f"  >> BEST SCORE in this scenario : {best[0]}  (score={best[5]:+.0f})")
    print()
    return results


# ==== Run les 3 scénarios principaux ====
r1 = run_scenario("SCENARIO 1 — optimistic (original backtester)", 0.0, False)
r2 = run_scenario("SCENARIO 2 — realistic (haircut 25%, after_queue)", 0.25, True)
r3 = run_scenario("SCENARIO 3 — pessimistic (haircut 50%, after_queue)", 0.50, True)

# ==== Decision matrix : quelle config gagne dans combien de scénarios ? ====
print("=" * 110)
print("DECISION MATRIX — classement total (optimistic + realistic + pessimistic)")
print("=" * 110)
labels = [c[0] for c in CONFIGS]
print(f"{'Config':<45s}  {'S1 opt':>8s}  {'S2 real':>9s}  {'S3 pess':>9s}  {'SUM':>8s}")
for i, label in enumerate(labels):
    s1 = r1[i][5]
    s2 = r2[i][5]
    s3 = r3[i][5]
    total_score = s1 + s2 + s3
    print(f"{label:<45s}  {s1:>+8.0f}  {s2:>+9.0f}  {s3:>+9.0f}  {total_score:>+8.0f}")
