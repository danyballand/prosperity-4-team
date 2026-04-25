"""
Le live R3 tourne sur fenêtre 0-100k (100k ticks). Tester EXACTEMENT cette fenêtre
sur chacun des 3 jours pour voir si v6 a un comportement différent du PnL 1M.

Si v6 PnL_0_100k >> PnL_1M/10 sur certains jours → on biaise la stratégie
pour optimiser cette fenêtre spécifique vs 3-day total.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
import local_backtest_r3 as lb
from local_backtest_r3 import simulate

print("=" * 90, flush=True)
print("TEST FENÊTRE 0-100k vs 1M complet — v6 baseline", flush=True)
print("=" * 90, flush=True)

windows_to_test = [
    ("0_25k",   25_000),
    ("0_50k",   50_000),
    ("0_100k",  100_000),
    ("0_200k",  200_000),
    ("0_500k",  500_000),
    ("0_1M",    1_000_000),
]

for d in (0, 1, 2):
    print(f"\n--- Jour {d} ---", flush=True)
    for label, max_ts in windows_to_test:
        pnl = simulate(d, max_ts=max_ts)
        total = sum(pnl.values())
        # Top 3 contributors
        top3 = sorted(pnl.items(), key=lambda x: -abs(x[1]))[:3]
        top_str = "  ".join(f"{lb._short(p)}:{v:+.0f}" for p, v in top3)
        print(f"  {label:<10s}  TOTAL={total:>+8.0f}  top: {top_str}", flush=True)

print(flush=True)
print("=" * 90, flush=True)
print("Si fenêtre 0-100k diffère du 1M (en pos/neg ou par produit), pivot strat.", flush=True)
print("=" * 90, flush=True)
