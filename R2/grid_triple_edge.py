"""
Teste différentes distributions triple_edge côté Osmium.
Le code original est hardcodé 55/30/15, on patche trade_product pour tester d'autres.

Méthode : monkey-patch trade_product via remplacement string.
"""
import sys
import os
import re
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
R1_DIR = os.path.abspath(os.path.join(HERE, "..", "R1"))
sys.path.insert(0, R1_DIR)
sys.path.insert(0, HERE)

# Import pour get baseline
import trader as trader_module
from grid_search_r2 import run_config

def main():
    baseline_grand, _, _ = run_config("baseline")
    print(f"[BASELINE] TOTAL={baseline_grand:+.0f}")
    print()

    # On ne peut pas easily monkey-patch trade_product sans réécrire. Alternative :
    # Patcher directement les constantes 55/30/15 dans le code source runtime via inspect/exec.
    # Plus propre : écrire un trader dérivé qui redéfinit trade_product.
    # Plus simple pour le moment : tester via un fichier trader séparé.

    # Test 1: override triple_edge ratios via dérivé
    import types
    import copy

    # Get the source of trade_product
    import inspect
    src = inspect.getsource(trader_module.trade_product)

    # Tester différents ratios
    ratios_to_test = [
        (55, 30, 15, "baseline 55/30/15"),
        (40, 40, 20, "40/40/20"),
        (60, 25, 15, "60/25/15"),
        (50, 30, 20, "50/30/20"),
        (70, 20, 10, "70/20/10"),
        (80, 15, 5, "80/15/5"),
        (100, 0, 0, "100/0/0 (single tier)"),
        (33, 33, 34, "tiers égaux"),
    ]

    print(f"{'Config':<30} {'Total':>10} {'Delta':>8}")
    print("-" * 50)

    for r1, r2, r3, label in ratios_to_test:
        # Patche le source string
        new_src = src
        new_src = new_src.replace("b1 = remaining_buy * 55 // 100", f"b1 = remaining_buy * {r1} // 100")
        new_src = new_src.replace("b2 = remaining_buy * 30 // 100", f"b2 = remaining_buy * {r2} // 100")
        new_src = new_src.replace("s1 = remaining_sell * 55 // 100", f"s1 = remaining_sell * {r1} // 100")
        new_src = new_src.replace("s2 = remaining_sell * 30 // 100", f"s2 = remaining_sell * {r2} // 100")
        # b3 = remaining_buy - b1 - b2  (calcul auto donc pas à patcher)

        # Exec the new source into a namespace with trader_module globals
        ns = {}
        ns.update(trader_module.__dict__)
        exec(new_src, ns)
        new_trade_product = ns["trade_product"]

        # Monkey-patch
        old_fn = trader_module.trade_product
        trader_module.trade_product = new_trade_product

        try:
            g, _, _ = run_config(label)
            delta = g - baseline_grand
            marker = "  ⭐" if delta > 50 else ""
            print(f"{label:<30} {g:>+10.0f} {delta:>+8.0f}{marker}")
        finally:
            trader_module.trade_product = old_fn


if __name__ == "__main__":
    main()
