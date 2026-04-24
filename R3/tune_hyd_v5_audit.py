"""
V5 AUDIT HARDENED — tester les 4 fixes de l'audit externe sur HYDROGEL_PACK :

Audit findings :
  P1. FV capped at 9995 quand mid descend à 9915 (clip=10 trop étroit)
  P1. take_width=0 = falling-knife buyer pendant selloff
  P2. Pas de trend_guard sur HYD -> rien ne coupe l'accumulation long
  P2. Pas de kill switch à position_limit -> reste +200 pendant toute la chute

Cibles :
  - worst 100k ts day 2 : >= 0 (actuellement -2,446)
  - total 3 jours        : >= +60k (actuellement +72,392)
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_HYD = dict(PP["HYDROGEL_PACK"])


def reset_hyd():
    PP["HYDROGEL_PACK"].clear()
    PP["HYDROGEL_PACK"].update(BASE_HYD)


def set_hyd(**kwargs):
    reset_hyd()
    for k, v in kwargs.items():
        PP["HYDROGEL_PACK"][k] = v


def bt_full_3days():
    total = 0.0
    per_day = {}
    for d in (0, 1, 2):
        pnl = simulate(d)
        per_day[d] = (sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0.0))
        total += sum(pnl.values())
    return total, per_day


def bt_day2_first_100k():
    pnl = simulate(2, max_ts=100_000)
    return sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0.0)


# Trend_guard preset "moderate" — s'active day_progress>=0.15 (tôt)
# Thresholds ajustés pour HYD (volatile autour 10k, pas structural drift)
TG_PRESET = dict(
    trend_guard=True,
    trend_guard_start=0.15,          # s'active à 15% de la journée
    trend_guard_short_window=8,
    trend_guard_long_window=40,
    trend_guard_short_threshold=-3.0,
    trend_guard_long_threshold=-8.0,
    trend_guard_min_bias=0,          # coupe accumulation long quand momentum neg
)

# V1 baseline = config actuelle (v4 = G)
V1_CURRENT = dict(
    fixed_fv=10000, adaptive_fixed_fv=True,
    fixed_fv_book_blend=0.50, fixed_fv_book_clip=10.0,
    make_edge=97, take_width=0, position_limit=200,
)

SCENARIOS = [
    ("V1. current v4 (clip=10, tw=0, lim=200)",
     {**V1_CURRENT}),

    # --- Fix 1 seul : widen clip (laisse FV suivre la dérive réelle) ---
    ("V2. clip=30 (widen)",
     {**V1_CURRENT, "fixed_fv_book_clip": 30.0}),
    ("V3. clip=50",
     {**V1_CURRENT, "fixed_fv_book_clip": 50.0}),
    ("V4. clip=100 (~=pure book)",
     {**V1_CURRENT, "fixed_fv_book_clip": 100.0}),

    # --- Fix 2 seul : take_width > 0 (stop falling knife) ---
    ("V5. clip=10 tw=1",
     {**V1_CURRENT, "take_width": 1}),
    ("V6. clip=10 tw=2",
     {**V1_CURRENT, "take_width": 2}),
    ("V7. clip=10 tw=3",
     {**V1_CURRENT, "take_width": 3}),

    # --- Combo clip + take_width ---
    ("V8. clip=30 tw=1",
     {**V1_CURRENT, "fixed_fv_book_clip": 30.0, "take_width": 1}),
    ("V9. clip=30 tw=2",
     {**V1_CURRENT, "fixed_fv_book_clip": 30.0, "take_width": 2}),
    ("V10. clip=50 tw=2",
     {**V1_CURRENT, "fixed_fv_book_clip": 50.0, "take_width": 2}),

    # --- Fix 3 seul : trend_guard (coupe l'accumulation long en selloff) ---
    ("V11. clip=10 tw=0 +trend_guard",
     {**V1_CURRENT, **TG_PRESET}),
    ("V12. clip=30 tw=1 +trend_guard",
     {**V1_CURRENT, "fixed_fv_book_clip": 30.0, "take_width": 1, **TG_PRESET}),
    ("V13. clip=50 tw=2 +trend_guard (FULL AUDIT)",
     {**V1_CURRENT, "fixed_fv_book_clip": 50.0, "take_width": 2, **TG_PRESET}),

    # --- Fix 4 : position_limit réduit (limite la casse max) ---
    ("V14. lim=100 clip=30 tw=1",
     {**V1_CURRENT, "position_limit": 100, "fixed_fv_book_clip": 30.0, "take_width": 1}),
    ("V15. lim=80 clip=30 tw=1 +trend_guard",
     {**V1_CURRENT, "position_limit": 80, "fixed_fv_book_clip": 30.0, "take_width": 1, **TG_PRESET}),
    ("V16. lim=100 clip=50 tw=2 +trend_guard",
     {**V1_CURRENT, "position_limit": 100, "fixed_fv_book_clip": 50.0, "take_width": 2, **TG_PRESET}),

    # --- Extreme : pure wall_mid (comme VE) ---
    ("V17. pure wall_mid tw=1 edge=3",
     {"fixed_fv": None, "use_microprice": True, "make_edge": 3, "take_width": 1, "position_limit": 200}),
    ("V18. pure wall_mid tw=2 edge=5 lim=100",
     {"fixed_fv": None, "use_microprice": True, "make_edge": 5, "take_width": 2, "position_limit": 100}),
]

print("=" * 100)
print("V5 AUDIT HARDENED — grid des 4 fixes audit")
print("=" * 100)
print(f"{'Scenario':<48s}  {'3day':>8s}  {'HYD 3d':>8s}  {'100k':>8s}  {'HYD 100k':>9s}")
print("-" * 100)

results = []
for (label, cfg) in SCENARIOS:
    set_hyd(**cfg)
    total_3d, per_day = bt_full_3days()
    hyd_3d = sum(per_day[d][1] for d in (0, 1, 2))
    total_100k, hyd_100k = bt_day2_first_100k()
    print(f"{label:<48s}  {total_3d:>+8.0f}  {hyd_3d:>+8.0f}  {total_100k:>+8.0f}  {hyd_100k:>+9.0f}")
    results.append((label, cfg, total_3d, hyd_3d, total_100k, hyd_100k))

print("-" * 100)
print()

# Rankings
best_3d = max(results, key=lambda r: r[2])
best_100k = max(results, key=lambda r: r[4])
# Robust = max(worst 100k) parmi ceux qui gardent 3day >= 60k
robust_candidates = [r for r in results if r[2] >= 60000]
best_robust = max(robust_candidates, key=lambda r: r[4]) if robust_candidates else None
# Trade-off 60/40 (privilégie un peu le 100k vs le précédent 70/30)
best_both = max(results, key=lambda r: r[2] * 0.6 + r[4] * 2.0)  # poids fort sur worst 100k

print(f"BEST 3day total         : {best_3d[0]}  (3d={best_3d[2]:+.0f}, 100k={best_3d[4]:+.0f})")
print(f"BEST worst 100k         : {best_100k[0]}  (3d={best_100k[2]:+.0f}, 100k={best_100k[4]:+.0f})")
if best_robust:
    print(f"BEST robust (3d>=60k)   : {best_robust[0]}  (3d={best_robust[2]:+.0f}, 100k={best_robust[4]:+.0f})")
print(f"BEST trade-off w×100k   : {best_both[0]}  (3d={best_both[2]:+.0f}, 100k={best_both[4]:+.0f})")
