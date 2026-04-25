"""
Bio-Pods — FULL grid search robuste.

On n'a testé que b1 ≈ 750 car c'est ce que suggère le Nash symétrique. Mais :
  - Si b1 = 800, on capture 27/51 counterparties au lieu de 17/51
  - Profit par trade plus bas (120 au lieu de 170) mais volume × 1.6
  - Contribution b1-arm seule : (27/51) × 120 = 63.5  vs  (17/51) × 170 = 56.7

On teste sur les 3 distributions + bootstrap pour toute la grille (b1, b2).
"""
import math
import random
from manual_biopods import RESERVES, SALE, expected_profit
from manual_biopods_robust import avg_b2_nash_heavy, avg_b2_naive_heavy, avg_b2_greedy_heavy


def worst_case_E(b1, b2, distributions):
    Es = [expected_profit(b1, b2, avg) for avg, _ in distributions]
    return min(Es), sum(Es) / len(Es)


def bootstrap_stats(b1, b2, pop, n=200, k=50, seed=42):
    random.seed(seed)
    profits = []
    for _ in range(n):
        sample = random.choices(pop, k=k)
        avg = sum(sample) / len(sample)
        profits.append(expected_profit(b1, b2, avg))
    profits.sort()
    mean = sum(profits) / len(profits)
    var = sum((p - mean) ** 2 for p in profits) / len(profits)
    return mean, math.sqrt(var), profits[int(0.05 * len(profits))]


distributions = [avg_b2_nash_heavy(), avg_b2_naive_heavy(), avg_b2_greedy_heavy()]
dist_labels = ["D1 Nash", "D2 Naive", "D3 Greedy"]
_, pop_d1 = distributions[0]

print("=" * 110)
print("FULL grid (b1, b2) — Top par critère worst-case min-E")
print("=" * 110)

all_results = []
for b1 in RESERVES:
    for b2 in RESERVES:
        if b2 <= b1:
            continue
        mn, mean = worst_case_E(b1, b2, distributions)
        all_results.append((b1, b2, mn, mean))

all_results.sort(key=lambda r: -r[2])
print(f"{'rank':>4s}  {'b1':>4s}  {'b2':>4s}  {'min_E':>8s}  {'mean_E':>8s}")
for i, (b1, b2, mn, mean) in enumerate(all_results[:15], 1):
    print(f"{i:>4d}  {b1:>4d}  {b2:>4d}  {mn:>+8.2f}  {mean:>+8.2f}")

print()
print("=" * 110)
print("FULL grid — Top par critère mean-E")
print("=" * 110)
by_mean = sorted(all_results, key=lambda r: -r[3])
print(f"{'rank':>4s}  {'b1':>4s}  {'b2':>4s}  {'min_E':>8s}  {'mean_E':>8s}")
for i, (b1, b2, mn, mean) in enumerate(by_mean[:15], 1):
    print(f"{i:>4d}  {b1:>4d}  {b2:>4d}  {mn:>+8.2f}  {mean:>+8.2f}")

print()
print("=" * 110)
print("Top-10 par mean E avec détail par distribution + bootstrap D1")
print("=" * 110)
header = f"{'b1':>4s}  {'b2':>4s}  " + "  ".join(f"{l:>9s}" for l in dist_labels) + f"  {'min':>8s}  {'boot_mean':>9s}  {'boot_std':>8s}  {'boot_q5':>7s}"
print(header)
print("-" * 110)
for (b1, b2, mn, mean) in by_mean[:10]:
    Es = [expected_profit(b1, b2, avg) for avg, _ in distributions]
    bm, bs, q5 = bootstrap_stats(b1, b2, pop_d1)
    row = f"{b1:>4d}  {b2:>4d}  " + "  ".join(f"{e:>+9.2f}" for e in Es) + f"  {mn:>+8.2f}  {bm:>+9.2f}  {bs:>8.2f}  {q5:>+7.2f}"
    print(row)

print()
print("=" * 110)
print("Check STRUCTUREL : profit par arm si b2 >= avg_b2 (pas de pénalité)")
print("=" * 110)
print(f"{'b1':>4s}  {'b2':>4s}  {'#r<=b1':>6s}  {'#b1<r<=b2':>10s}  {'arm1':>6s}  {'arm2':>6s}  {'total':>6s}")
# b2 = 850 fixe, on fait varier b1
for b1 in range(700, 861, 10):
    b2 = 850
    if b2 <= b1:
        continue
    n_arm1 = sum(1 for r in RESERVES if r <= b1)
    n_arm2 = sum(1 for r in RESERVES if b1 < r <= b2)
    arm1 = n_arm1 * (SALE - b1) / len(RESERVES)
    arm2 = n_arm2 * (SALE - b2) / len(RESERVES)
    print(f"{b1:>4d}  {b2:>4d}  {n_arm1:>6d}  {n_arm2:>10d}  {arm1:>+6.2f}  {arm2:>+6.2f}  {arm1+arm2:>+6.2f}")

print()
print("=" * 110)
print("VERDICT")
print("=" * 110)
c_reco_current = (750, 835)
c1_min, c1_mean = worst_case_E(*c_reco_current, distributions)
best_min = all_results[0]
best_mean = by_mean[0]
print(f"Reco actuelle (Nash)     : b1={c_reco_current[0]}, b2={c_reco_current[1]}  min_E={c1_min:+.2f}  mean_E={c1_mean:+.2f}")
print(f"Meilleur min_E (robuste) : b1={best_min[0]}, b2={best_min[1]}  min_E={best_min[2]:+.2f}  mean_E={best_min[3]:+.2f}")
print(f"Meilleur mean_E          : b1={best_mean[0]}, b2={best_mean[1]}  min_E={best_mean[2]:+.2f}  mean_E={best_mean[3]:+.2f}")
print()
print(f"Gap worst-case vs Nash : {best_min[2] - c1_min:+.2f} SS/trade")
print(f"Gap moyen vs Nash      : {best_mean[3] - c1_mean:+.2f} SS/trade")
