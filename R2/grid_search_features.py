"""
Grid search sur les FEATURES (flags on/off + structures alternatives) — pas juste params.

Tests :
  - triple_edge ratios alternatifs
  - inclusive_take Osm
  - adaptive_fixed_fv Osm (réactivé avec params grid)
  - use_obi_skew Osm (grid sur obi_strength)
  - use_microprice Osm (True vs wall_mid)
  - pennying OFF sur Osm
  - take_width Osm > 0
  - min_pennying_edge sweep
  - use_kalman OFF sur Pepper (tester wall_mid seul)
"""
import sys
import os
import copy
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from grid_search_r2 import run_config, DAYS, PRODUCTS


def main():
    print("=" * 80)
    print("GRID FEATURES v31 sur CSV R2 — baseline +27,097")
    print("=" * 80)

    # baseline
    baseline_grand, _, _ = run_config("baseline")
    print(f"\n[BASELINE] TOTAL={baseline_grand:+.0f}")

    configs = [
        # === triple_edge ratios alternatifs (code hardcodé 55/30/15, on peut pas changer sans patch)
        # skip — nécessite patch code direct
        # === pennying OFF Osm
        ("pennying OFF Osm", {"pennying": False}, None),
        ("min_penny_edge=0 Osm", {"min_pennying_edge": 0}, None),
        ("min_penny_edge=2 Osm", {"min_pennying_edge": 2}, None),
        ("min_penny_edge=3 Osm", {"min_pennying_edge": 3}, None),
        # === inclusive_take Osm
        ("inclusive_take Osm", {"inclusive_take": True}, None),
        # === take_width Osm > 0
        ("take_width=1 Osm", {"take_width": 1}, None),
        ("take_width=2 Osm", {"take_width": 2}, None),
        ("take_width=3 Osm", {"take_width": 3}, None),
        # === triple_edge OFF / double_edge ON
        ("triple_edge OFF Osm (single layer)", {"triple_edge": False, "double_edge": False}, None),
        ("double_edge Osm", {"triple_edge": False, "double_edge": True}, None),
        # === inventory_aware_take OFF
        ("inventory_aware_take OFF Osm", {"inventory_aware_take": False}, None),
        ("take_skew_mult=1.0 Osm", {"take_skew_multiplier": 1.0}, None),
        ("take_skew_mult=3.0 Osm", {"take_skew_multiplier": 3.0}, None),
        # === inventory_clearing OFF
        ("inventory_clearing OFF Osm", {"inventory_clearing": False}, None),
        ("clear_urgent_frac=0.4 Osm", {"clearing_urgent_fraction": 0.4}, None),
        ("clear_urgent_frac=0.8 Osm", {"clearing_urgent_fraction": 0.8}, None),
        # === microprice vs wall_mid Osm
        ("use_microprice Osm", {"use_microprice": True}, None),
        # === OBI skew Osm (rejeté en handoff, on re-teste plus doucement)
        ("obi_skew strength=0.25", {"use_obi_skew": True, "obi_strength": 0.25}, None),
        ("obi_skew strength=0.5", {"use_obi_skew": True, "obi_strength": 0.5}, None),
        ("obi_skew strength=1.0", {"use_obi_skew": True, "obi_strength": 1.0}, None),
        # === adaptive_fixed_fv Osm (rejeté, on re-teste params fins)
        ("adaptive_fv blend=0.25", {"adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.25, "fixed_fv_book_clip": 2.0}, None),
        ("adaptive_fv blend=0.50", {"adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.50, "fixed_fv_book_clip": 2.0}, None),
        ("adaptive_fv blend=0.75", {"adaptive_fixed_fv": True, "fixed_fv_book_blend": 0.75, "fixed_fv_book_clip": 2.0}, None),
        ("adaptive_fv blend=1.0 (pur)", {"adaptive_fixed_fv": True, "fixed_fv_book_blend": 1.0, "fixed_fv_book_clip": 5.0}, None),
        # === PEPPER variants
        ("Pep use_kalman OFF", None, {"use_kalman": False}),
        ("Pep use_microprice OFF", None, {"use_microprice": False}),
        ("Pep kalman_drift=1.0", None, {"kalman_drift": 1.0}),
        ("Pep kalman_drift=5.0", None, {"kalman_drift": 5.0}),
        ("Pep kalman_R=100 (plus réactif)", None, {"kalman_R": 100.0}),
        ("Pep kalman_R=400 (moins réactif)", None, {"kalman_R": 400.0}),
        ("Pep trend_guard OFF", None, {"trend_guard": False}),
        ("Pep hold_until=0.90", None, {"hold_bias_until": 0.90}),
        ("Pep hold_until=1.0", None, {"hold_bias_until": 1.0}),
        ("Pep bootstrap_target=70", None, {"bootstrap_target": 70}),
        ("Pep bootstrap_target=80", None, {"bootstrap_target": 80}),
        ("Pep id_markout OFF", None, {"id_markout": False}),
    ]

    print(f"\n{'Config':<45} {'Total':>10} {'Delta':>8}")
    print("-" * 80)
    results = []
    for label, osm_o, pep_o in configs:
        g, _, _ = run_config(label, osm_overrides=osm_o, pep_overrides=pep_o)
        delta = g - baseline_grand
        marker = "  ⭐" if delta > 50 else ("  ❌" if delta < -200 else "")
        print(f"{label:<45} {g:>+10.0f} {delta:>+8.0f}{marker}")
        results.append((label, g, delta, osm_o, pep_o))

    # Top 5 gagnants
    print("\n" + "=" * 80)
    print("TOP 5 GAINS (delta > 0)")
    print("=" * 80)
    winners = sorted([r for r in results if r[2] > 0], key=lambda x: -x[2])[:5]
    for label, g, d, osm_o, pep_o in winners:
        print(f"  +{d:>5.0f}  {label:<40}  osm={osm_o}  pep={pep_o}")

    # Stackés top 3
    if len(winners) >= 2:
        print("\n" + "=" * 80)
        print("COMBINAISON TOP 3 GAINS")
        print("=" * 80)
        combined_osm = {}
        combined_pep = {}
        for _, _, _, osm_o, pep_o in winners[:3]:
            if osm_o: combined_osm.update(osm_o)
            if pep_o: combined_pep.update(pep_o)
        g, t, pd = run_config("TOP3 STACKED", osm_overrides=combined_osm, pep_overrides=combined_pep)
        print(f"  osm={combined_osm}")
        print(f"  pep={combined_pep}")
        print(f"  TOTAL={g:+.0f}  delta={g-baseline_grand:+.0f}  day-1={sum(pd[-1].values()):+.0f}  day0={sum(pd[0].values()):+.0f}  day+1={sum(pd[1].values()):+.0f}")


if __name__ == "__main__":
    main()
