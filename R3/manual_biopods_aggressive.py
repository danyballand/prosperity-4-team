"""
Bio-Pods AGRESSIF : maximiser E[profit] sous priors réalistes population IMC Prosperity.

Hypothèse : la population IMC n'est pas uniformément répartie 1/3 Nash / 1/3 Naive / 1/3 Greedy.
Probablement :
  - 50% Nash-aware (copié du forum/manual prosperity)
  - 35% Naive (simple heuristique)
  - 15% Greedy (agressif high b2)

Objectif : trouver (b1, b2) qui maximise E[profit] sous ce prior,
pas le min robuste. On accepte plus de variance pour plus de upside.
"""
import math
from manual_biopods import RESERVES, SALE, expected_profit
from manual_biopods_robust import avg_b2_nash_heavy, avg_b2_naive_heavy, avg_b2_greedy_heavy

avg_nash, _ = avg_b2_nash_heavy()
avg_naive, _ = avg_b2_naive_heavy()
avg_greedy, _ = avg_b2_greedy_heavy()

print(f"Distributions : Nash avg_b2={avg_nash:.1f}, Naive={avg_naive:.1f}, Greedy={avg_greedy:.1f}")
print()

# 3 priors différents pour illustrer la sensibilité
priors = [
    ("Equilibré", (0.33, 0.33, 0.34)),
    ("Nash-heavy (prior conservateur)", (0.50, 0.35, 0.15)),
    ("Naive-heavy (prior agressif)", (0.30, 0.55, 0.15)),
    ("Très Nash (forum-driven)", (0.70, 0.25, 0.05)),
    ("Très Naive (forum absent)", (0.15, 0.70, 0.15)),
]


def E_weighted(b1, b2, weights):
    w1, w2, w3 = weights
    return (w1 * expected_profit(b1, b2, avg_nash)
            + w2 * expected_profit(b1, b2, avg_naive)
            + w3 * expected_profit(b1, b2, avg_greedy))


for label, weights in priors:
    results = []
    for b1 in RESERVES:
        for b2 in RESERVES:
            if b2 <= b1:
                continue
            e = E_weighted(b1, b2, weights)
            e_nash = expected_profit(b1, b2, avg_nash)
            e_naive = expected_profit(b1, b2, avg_naive)
            e_greedy = expected_profit(b1, b2, avg_greedy)
            results.append((b1, b2, e, e_nash, e_naive, e_greedy))
    results.sort(key=lambda r: -r[2])

    print("=" * 100)
    print(f"PRIOR : {label}  weights={weights}")
    print("=" * 100)
    print(f"{'rank':>4s}  {'b1':>4s}  {'b2':>4s}  {'E_priors':>9s}  "
          f"{'E_nash':>8s}  {'E_naive':>8s}  {'E_greedy':>9s}  {'downside':>9s}")
    for i, (b1, b2, e, en, ena, eg) in enumerate(results[:10], 1):
        downside = min(en, ena, eg)
        print(f"{i:>4d}  {b1:>4d}  {b2:>4d}  {e:>+9.2f}  "
              f"{en:>+8.2f}  {ena:>+8.2f}  {eg:>+9.2f}  {downside:>+9.2f}")
    print()


# Comparaison directe : robust (760, 855) vs candidats agressifs
print("=" * 100)
print("COMPARAISON : robust (760, 855) vs agressif pour chaque prior")
print("=" * 100)

candidates = [
    (760, 855, "ROBUST (inv)"),
    (760, 850, "AGRO-850"),
    (755, 850, "AGRO-755/850"),
    (760, 845, "ULTRA-AGRO-845"),
    (760, 840, "ULTRA-AGRO-840"),
    (770, 850, "AGRO-high-b1"),
]

print(f"{'candidat':<18s}  " + "  ".join(f"{p[0]:<13s}" for p in priors))
for b1, b2, label in candidates:
    row = f"{label:<18s}  "
    for _, weights in priors:
        e = E_weighted(b1, b2, weights)
        row += f"{e:>+13.2f}  "
    print(row)

print()
print("=" * 100)
print("GAIN ABSOLU (× 51 counterparties) vs robust (760, 855)")
print("=" * 100)
baseline = {}
for prior_label, weights in priors:
    baseline[prior_label] = E_weighted(760, 855, weights)

print(f"{'candidat':<18s}  " + "  ".join(f"{p[0][:13]:<13s}" for p in priors))
for b1, b2, label in candidates:
    if (b1, b2) == (760, 855):
        continue
    row = f"{label:<18s}  "
    for prior_label, weights in priors:
        e = E_weighted(b1, b2, weights)
        gap = (e - baseline[prior_label]) * 51
        row += f"{gap:>+13.1f}  "
    print(row)
