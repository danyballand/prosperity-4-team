"""
Final pick : compare V10 variants + pick best robust config
Critere : (worst 100k min sur les 3 days) — c'est la pire live-equivalent possible
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trader_r3 as tm
from local_backtest_r3 import simulate

PP = tm.PRODUCT_PARAMS
BASE_HYD = dict(PP["HYDROGEL_PACK"])

def set_hyd(**kwargs):
    PP["HYDROGEL_PACK"].clear()
    PP["HYDROGEL_PACK"].update(BASE_HYD)
    for k, v in kwargs.items():
        PP["HYDROGEL_PACK"][k] = v

def eval_cfg(**cfg):
    set_hyd(**cfg)
    results = {"3d": 0.0, "hyd3d": 0.0, "days": {}, "100k": {}}
    for d in (0, 1, 2):
        pnl = simulate(d)
        results["3d"] += sum(pnl.values())
        results["hyd3d"] += pnl.get("HYDROGEL_PACK", 0.0)
        results["days"][d] = (sum(pnl.values()), pnl.get("HYDROGEL_PACK", 0.0))
        pnl_100 = simulate(d, max_ts=100_000)
        results["100k"][d] = (sum(pnl_100.values()), pnl_100.get("HYDROGEL_PACK", 0.0))
    return results


CANDIDATES = [
    ("V1_current (c10 tw0)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=10.0, make_edge=97, take_width=0, position_limit=200)),
    ("V10 (c50 tw2)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=50.0, make_edge=97, take_width=2, position_limit=200)),
    ("alt1 (c30 tw2)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=30.0, make_edge=97, take_width=2, position_limit=200)),
    ("alt2 (c50 tw3)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=50.0, make_edge=97, take_width=3, position_limit=200)),
    ("alt3 (c75 tw3)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=75.0, make_edge=97, take_width=3, position_limit=200)),
    ("alt4 (c30 tw1 lim=100)",
     dict(fixed_fv=10000, adaptive_fixed_fv=True, fixed_fv_book_blend=0.50, fixed_fv_book_clip=30.0, make_edge=97, take_width=1, position_limit=100)),
]

print("=" * 110)
print("Final picks — worst 100k across ALL 3 days (pire live-equivalent possible)")
print("=" * 110)
print(f"{'Config':<25s}  {'3d':>8s}  {'HYD3d':>8s}  " +
      "  ".join(f"d{d}_100k" for d in (0,1,2)) + f"  {'min100k':>8s}")
print("-" * 110)
for label, cfg in CANDIDATES:
    r = eval_cfg(**cfg)
    d100 = [r["100k"][d][1] for d in (0,1,2)]  # HYD only
    min_hyd = min(d100)
    total_100 = [r["100k"][d][0] for d in (0,1,2)]
    min_total = min(total_100)
    print(f"{label:<25s}  {r['3d']:>+8.0f}  {r['hyd3d']:>+8.0f}  " +
          "  ".join(f"{v:>+7.0f}" for v in total_100) + f"  {min_total:>+8.0f}")
    print(f"{'  └ HYD only':<25s}  {'':>8s}  {'':>8s}  " +
          "  ".join(f"{v:>+7.0f}" for v in d100) + f"  {min_hyd:>+8.0f}")
