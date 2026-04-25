"""
Bio-Pods — analyse robuste sous 3 distributions d'avg_b2.

L'hypothèse "symmetric Nash" du fichier manual_biopods.py suppose que TOUS les
joueurs jouent le même b2 optimal. En pratique sur Prosperity, beaucoup de teams
jouent naively (pas de Nash) ou par intuition (greedy, défensif, etc.).

La pénalité cubique ((920 - avg_b2) / (920 - b2))^3 est non-linéaire : un
décalage de 20 points sur avg_b2 peut coûter 30% du profit par trade.

On teste la reco (750, 835) et des alternatives contre 3 distributions :

  D1 — Nash-heavy : 60% joueurs jouent 830-840, 20% naïfs 780-800, 20% greedy 860+
       → avg_b2 ≈ 830
  D2 — Naive-heavy : 30% Nash, 40% naïfs 770-810, 30% random uniforme 700-900
       → avg_b2 ≈ 810
  D3 — Greedy-heavy : 30% Nash, 20% naïfs, 50% greedy 870-900
       → avg_b2 ≈ 865

Critère : maximiser le MIN E[profit] à travers les 3 distributions
(robustesse > optimum local).
"""
import math
from manual_biopods import RESERVES, SALE, expected_profit


# ============== Modèles de distribution avg_b2 ==============

def avg_b2_nash_heavy():
    """D1 : 60% Nash players around 835, 20% naive 780-800, 20% greedy 860-900"""
    nash = [830, 835, 835, 835, 835, 840] * 10    # 60
    naive = [780, 785, 790, 795, 800] * 4          # 20
    greedy = [860, 870, 880, 890, 900] * 4         # 20
    pop = nash + naive + greedy
    return sum(pop) / len(pop), pop

def avg_b2_naive_heavy():
    """D2 : 30% Nash, 40% naive 770-810, 30% random uniform 700-900"""
    nash = [830, 835, 840] * 10                    # 30
    naive = [770, 780, 790, 800, 810] * 8          # 40
    # random uniform 700-900, step 20
    rand = list(range(700, 901, 20))               # 11
    rand = rand * 3                                # 33
    pop = nash + naive + rand
    return sum(pop) / len(pop), pop

def avg_b2_greedy_heavy():
    """D3 : 30% Nash, 20% naive, 50% greedy 870-900"""
    nash = [830, 835, 840] * 10                    # 30
    naive = [780, 790, 800, 810] * 5               # 20
    greedy = [870, 880, 885, 890, 895, 900] * 9    # 54
    pop = nash + naive + greedy[:50]
    return sum(pop) / len(pop), pop


def E_profit_over_distribution(b1, b2, distribution_pop):
    """
    Contrairement à expected_profit() qui prend un avg_b2 scalaire, ici on calcule
    E[profit] en intégrant sur la distribution RÉELLE de avg_b2. Mais comme avg_b2
    est une moyenne de population, c'est bien juste un scalaire une fois la
    population fixée. Donc équivalent à expected_profit avec avg_b2 = mean(pop).

    On garde la fonction pour clarifier et permettre éventuellement un modèle où
    avg_b2 est bruité (sampling d'une sous-population).
    """
    avg = sum(distribution_pop) / len(distribution_pop)
    return expected_profit(b1, b2, avg)


def E_profit_bootstrap(b1, b2, pop, n_samples=200, sample_size=50):
    """
    Modèle + réaliste : chaque round de trades, on fait face à un ÉCHANTILLON
    de counterparties (pas la population entière). Bootstrap : tirer n_samples
    sous-ensembles de taille sample_size, avg_b2 varie entre samples.
    Retourne mean + std de E[profit].
    """
    import random
    random.seed(42)
    profits = []
    for _ in range(n_samples):
        sample = random.choices(pop, k=sample_size)
        avg = sum(sample) / len(sample)
        profits.append(expected_profit(b1, b2, avg))
    mean = sum(profits) / len(profits)
    var = sum((p - mean) ** 2 for p in profits) / len(profits)
    return mean, math.sqrt(var)


# ============== MAIN ==============

print("=" * 100)
print("Bio-Pods — Robustesse sous 3 distributions avg_b2")
print("=" * 100)

distributions = [
    ("D1 Nash-heavy   ", avg_b2_nash_heavy()),
    ("D2 Naive-heavy  ", avg_b2_naive_heavy()),
    ("D3 Greedy-heavy ", avg_b2_greedy_heavy()),
]

print()
print("Distributions simulées :")
for name, (avg, pop) in distributions:
    s = sorted(pop)
    p25 = s[len(s)//4]
    p50 = s[len(s)//2]
    p75 = s[3*len(s)//4]
    print(f"  {name}  N={len(pop):3d}  mean={avg:6.1f}  p25={p25}  p50={p50}  p75={p75}")
print()

# ============== Candidates à tester ==============
CANDIDATES = [
    ("C1 Nash reco (750, 835)", 750, 835),
    ("C2 safer b2    (750, 840)", 750, 840),
    ("C3 aggressive  (750, 830)", 750, 830),
    ("C4 higher b1   (755, 835)", 755, 835),
    ("C5 higher b1   (760, 840)", 760, 840),
    ("C6 defensive   (750, 845)", 750, 845),
    ("C7 very safe   (750, 850)", 750, 850),
    ("C8 ultra safe  (750, 860)", 750, 860),
    ("C9 b1 +        (770, 840)", 770, 840),
    ("C10 greedy b2  (750, 870)", 750, 870),
]

print("=" * 100)
print("E[profit/trade] sous chaque distribution")
print("=" * 100)
header = f"{'Candidate':<28s}  " + "  ".join(f"{n[:12]:>12s}" for n, _ in distributions) + f"  {'min':>8s}  {'mean':>8s}"
print(header)
print("-" * 100)

rows = []
for label, b1, b2 in CANDIDATES:
    Es = []
    for name, (avg, pop) in distributions:
        e = expected_profit(b1, b2, avg)
        Es.append(e)
    mn = min(Es)
    mean = sum(Es) / len(Es)
    row = f"{label:<28s}  " + "  ".join(f"{e:>+12.2f}" for e in Es) + f"  {mn:>+8.2f}  {mean:>+8.2f}"
    print(row)
    rows.append((label, b1, b2, Es, mn, mean))

# ============== Bootstrap avec sampling ==============
print()
print("=" * 100)
print("Bootstrap (200 samples × 50 counterparties) : mean ± std sous D1 Nash-heavy")
print("=" * 100)
_, pop_d1 = avg_b2_nash_heavy()
print(f"{'Candidate':<28s}  {'mean':>8s}  {'std':>6s}  {'5%-q':>6s}  {'95%-q':>6s}")
print("-" * 70)

import random
for label, b1, b2 in CANDIDATES:
    random.seed(42)
    profits = []
    for _ in range(200):
        sample = random.choices(pop_d1, k=50)
        avg = sum(sample) / len(sample)
        profits.append(expected_profit(b1, b2, avg))
    profits.sort()
    mean = sum(profits) / len(profits)
    var = sum((p - mean) ** 2 for p in profits) / len(profits)
    std = math.sqrt(var)
    q5 = profits[int(0.05 * len(profits))]
    q95 = profits[int(0.95 * len(profits))]
    print(f"{label:<28s}  {mean:>+8.2f}  {std:>6.2f}  {q5:>+6.2f}  {q95:>+6.2f}")

# ============== Verdict ==============
print()
print("=" * 100)
print("VERDICT")
print("=" * 100)

# Best by min E (worst-case robustness)
best_min = max(rows, key=lambda r: r[4])
# Best by mean E (average across scenarios)
best_mean = max(rows, key=lambda r: r[5])

print(f"Max-min robuste (worst-case)  : {best_min[0]}  min E = {best_min[4]:+.2f} SS")
print(f"Max-mean (avg across scenarios): {best_mean[0]}  mean E = {best_mean[5]:+.2f} SS")
print()

# Combien le Nash actuel (C1 = 750, 835) perd-il vs max-min ?
c1 = rows[0]
if c1[4] < best_min[4]:
    delta = best_min[4] - c1[4]
    print(f"⚠ C1 Nash (750, 835) vs max-min : -{delta:.2f} SS/trade de gap dans le worst-case")
    print(f"  Sur ~500 trades typiques, ça fait -{delta * 500:.0f} SS")
else:
    print(f"✓ C1 Nash (750, 835) est le plus robuste — confirmé")
print()
