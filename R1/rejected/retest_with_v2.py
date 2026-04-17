"""
Re-test les architectures précédemment rejetées avec le backtester v2 fixé.
Baseline = v31 actuel (trader.py). Chaque variant = patch de params avant run.

On teste sur 3 jours tronqués à 100k ticks (comparable au live).
"""
import sys
import importlib
from collections import defaultdict


def reset_trader_module():
    """Force un reload propre de trader.py (remet PRODUCT_PARAMS à son état initial)."""
    for mod_name in ["trader", "local_backtest_v2"]:
        if mod_name in sys.modules:
            del sys.modules[mod_name]


def run_variant(name, patch_fn):
    """
    patch_fn : (trader_module) -> None, modifie PRODUCT_PARAMS sur place
    Retourne (total_day-2, total_day-1, total_day_0, grand_total)
    """
    reset_trader_module()
    import trader as tm
    import local_backtest_v2 as bt
    patch_fn(tm)
    per_day = []
    for day in [-2, -1, 0]:
        pnl, _, _, _ = bt.simulate(day, passive_fills=True)
        per_day.append((pnl["ASH_COATED_OSMIUM"], pnl["INTARIAN_PEPPER_ROOT"]))
    return per_day


def fmt_line(name, per_day, baseline_per_day=None):
    totals = [o + p for o, p in per_day]
    grand = sum(totals)
    if baseline_per_day is None:
        return f"{name:<40}  d-2={totals[0]:>+8.0f}  d-1={totals[1]:>+8.0f}  d0={totals[2]:>+8.0f}  TOTAL={grand:>+9.0f}"
    base_totals = [o + p for o, p in baseline_per_day]
    base_grand = sum(base_totals)
    delta = grand - base_grand
    marker = "✓✓" if delta > 500 else "✓" if delta > 100 else " " if abs(delta) <= 100 else "✗"
    return (f"{marker} {name:<40}  "
            f"Δd-2={totals[0]-base_totals[0]:>+6.0f}  "
            f"Δd-1={totals[1]-base_totals[1]:>+6.0f}  "
            f"Δd0={totals[2]-base_totals[2]:>+6.0f}  "
            f"Δtot={delta:>+6.0f}")


# ========================================================================
# Variant patches
# ========================================================================

def baseline(tm):
    pass  # v31 tel quel

def osmium_adaptive_fv(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["adaptive_fixed_fv"] = True

def osmium_obi_skew(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["use_obi_skew"] = True
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["obi_strength"] = 0.5

def pepper_bayes(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["use_bayes_ap"] = True

def pepper_no_microprice(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["use_microprice"] = False

def osmium_friend_weights(tm):
    # Pote 189905 : triple weights [40,30,30] normal, [25,30,45] one-sided
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["triple_buy_weights"] = [40, 30, 30]
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["triple_sell_weights"] = [40, 30, 30]
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["triple_buy_weights_one_sided"] = [25, 30, 45]
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["triple_sell_weights_one_sided"] = [25, 30, 45]

def osmium_friend_shadow_join(tm):
    # Pote 189905 : thin top shadow join qty=2
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["thin_top_shadow_join"] = True
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["thin_top_shadow_top_volume"] = 10
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["thin_top_shadow_min_spread"] = 8
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["thin_top_shadow_qty"] = 2
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["thin_top_shadow_max_abs_pos"] = 45

def osmium_friend_asymmetric_clearing(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["clearing_price_edge_long"] = 2
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["clearing_price_edge_short"] = 1
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["clearing_urgent_fraction_long"] = 0.75
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["clearing_urgent_fraction_short"] = 0.60

def osmium_friend_take_only_short(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["inventory_take_only_short"] = True

def osmium_friend_all(tm):
    osmium_friend_weights(tm)
    osmium_friend_shadow_join(tm)
    osmium_friend_asymmetric_clearing(tm)
    osmium_friend_take_only_short(tm)

def pepper_trend_guard_hold_30(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["trend_guard_min_bias"] = 30

def pepper_max_bias_40(tm):
    # Plus de bias max — accepter plus de drawdown
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["max_bias"] = 40

def pepper_max_bias_50(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["max_bias"] = 50

def pepper_bootstrap_offset_15(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["bootstrap_cap_offset"] = 15.0

def pepper_bootstrap_offset_5(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["bootstrap_cap_offset"] = 5.0

def osmium_make_edge_90(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["make_edge"] = 90

def osmium_make_edge_105(tm):
    tm.PRODUCT_PARAMS["ASH_COATED_OSMIUM"]["make_edge"] = 105

def pepper_take_width_0(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["take_width"] = 0

def pepper_take_width_5(tm):
    tm.PRODUCT_PARAMS["INTARIAN_PEPPER_ROOT"]["take_width"] = 5


# ========================================================================
# Run all
# ========================================================================
print("="*100)
print("RETEST AVEC BACKTESTER V2 (truncated 100k + passive fills)")
print("="*100)

print("\n--- 1. Baseline v31 ---")
base_per_day = run_variant("v31 baseline", baseline)
print(fmt_line("v31 baseline", base_per_day))

variants = [
    ("Osmium: adaptive_fixed_fv ON", osmium_adaptive_fv),
    ("Osmium: use_obi_skew ON (obi_str=0.5)", osmium_obi_skew),
    ("Osmium: friend weights [40,30,30]", osmium_friend_weights),
    ("Osmium: friend thin_top_shadow_join qty=2", osmium_friend_shadow_join),
    ("Osmium: friend asymmetric clearing", osmium_friend_asymmetric_clearing),
    ("Osmium: friend inv_take_only_short", osmium_friend_take_only_short),
    ("Osmium: friend ALL 4 combined", osmium_friend_all),
    ("Osmium: make_edge 90 (vs 97)", osmium_make_edge_90),
    ("Osmium: make_edge 105 (vs 97)", osmium_make_edge_105),
    ("Pepper: use_bayes_ap ON", pepper_bayes),
    ("Pepper: microprice OFF (wall_mid)", pepper_no_microprice),
    ("Pepper: trend_guard_min_bias=30", pepper_trend_guard_hold_30),
    ("Pepper: max_bias 30→40", pepper_max_bias_40),
    ("Pepper: max_bias 30→50", pepper_max_bias_50),
    ("Pepper: bootstrap_offset 9→15", pepper_bootstrap_offset_15),
    ("Pepper: bootstrap_offset 9→5", pepper_bootstrap_offset_5),
    ("Pepper: take_width 3→0", pepper_take_width_0),
    ("Pepper: take_width 3→5", pepper_take_width_5),
]

print("\n--- 2. Variants (Δ vs baseline) ---")
for name, fn in variants:
    try:
        per_day = run_variant(name, fn)
        print(fmt_line(name, per_day, base_per_day))
    except Exception as e:
        print(f"X {name:<40}  ERROR: {type(e).__name__}: {e}")

print("\nLégende: ✓✓ = +500 XIREC, ✓ = +100, (blanc) = ±100, ✗ = -100")
