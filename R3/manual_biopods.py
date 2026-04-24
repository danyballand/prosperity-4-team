"""
Manual challenge R3 — Ornamental Bio-Pods
=========================================

Règles wiki (transcription Dany) :
  - Reserves uniform {670, 675, ..., 920}  (51 valeurs, step 5)
  - Tu soumets deux bids b1 < b2
  - Un counterparty avec reserve r :
      * si b1 >= r  -> trade at b1
      * sinon si b2 >= r :
          - si b2 >= avg_b2_players : trade at b2 (full profit)
          - si b2 <  avg_b2_players : trade at b2 avec penalty = ((920-avg_b2)/(920-b2))^3
      * sinon -> pas de trade
  - Revente implicite à 920 (valeur haut de range, standard Prosperity)
  - Profit par trade = (920 - prix_payé) * penalty_factor

Objectif : trouver (b1, b2) qui maximise E[profit] sachant que avg_b2 est lui-même
le résultat de l'agrégation des best-responses (Nash équilibre approximatif).

Méthode :
  1) Grid search (b1, b2) dans {670..920}² avec b1 < b2
  2) Itération point fixe : partir avg_b2 = 800, calc best response, update avg_b2
  3) Converger vers équilibre, et lister top-5 bids robustes
"""
import math

RESERVES = list(range(670, 921, 5))   # 51 valeurs
SALE = 920                             # valeur de revente implicite


def expected_profit(b1, b2, avg_b2):
    """E[profit] par counterparty, uniformement tiré dans RESERVES."""
    if b2 <= b1:
        return -1.0  # invalide
    total = 0.0
    n = len(RESERVES)
    penalty = 1.0
    if b2 < avg_b2:
        # penalty = ((920-avg_b2)/(920-b2))^3
        penalty = ((SALE - avg_b2) / (SALE - b2)) ** 3 if SALE > b2 else 0.0
    for r in RESERVES:
        if b1 >= r:
            total += (SALE - b1)
        elif b2 >= r:
            total += (SALE - b2) * penalty
        # else 0
    return total / n


def best_response(avg_b2):
    """Grid over (b1, b2), retourne (b1*, b2*, E*)."""
    best = (None, None, -1.0)
    for b1 in RESERVES:
        for b2 in RESERVES:
            if b2 <= b1:
                continue
            e = expected_profit(b1, b2, avg_b2)
            if e > best[2]:
                best = (b1, b2, e)
    return best


def find_fixed_point(start=800, max_iter=30, tol=0.5):
    """Itération : avg_b2 = best_response(avg_b2)[1]. Convergence visuelle."""
    avg = start
    history = [avg]
    for it in range(max_iter):
        b1, b2, e = best_response(avg)
        print(f"  iter {it:>2}: avg_b2_in={avg:6.1f} -> BR (b1={b1}, b2={b2}, E={e:.2f})")
        if abs(b2 - avg) <= tol:
            return (b1, b2, e, avg)
        # relaxation douce : moyenne avec ancien pour éviter oscillations
        avg = 0.5 * avg + 0.5 * b2
        history.append(avg)
    return (b1, b2, e, avg)


def top_k_bids(avg_b2, k=10):
    """Top-k (b1, b2) triés par E[profit] descendant."""
    results = []
    for b1 in RESERVES:
        for b2 in RESERVES:
            if b2 <= b1:
                continue
            e = expected_profit(b1, b2, avg_b2)
            results.append((b1, b2, e))
    results.sort(key=lambda x: -x[2])
    return results[:k]


if __name__ == "__main__":
    print("=" * 72)
    print("R3 MANUAL — Ornamental Bio-Pods — bids optimaux")
    print("=" * 72)
    print(f"Reserves : {len(RESERVES)} valeurs uniformes {RESERVES[0]}..{RESERVES[-1]} step 5")
    print(f"Sale (revente hypothèse) : {SALE}")
    print()

    # ---------- Phase 1 : exploration pour avg_b2 hypothétiques ----------
    print("Phase 1 — meilleur (b1, b2) pour différentes hypothèses avg_b2 :")
    print(f"  {'avg_b2':>8s}  {'b1*':>5s}  {'b2*':>5s}  {'E[profit]':>10s}")
    for avg in (700, 750, 780, 800, 820, 840, 860, 880):
        b1, b2, e = best_response(avg)
        print(f"  {avg:>8.0f}  {b1:>5d}  {b2:>5d}  {e:>10.3f}")
    print()

    # ---------- Phase 2 : point fixe Nash ----------
    print("Phase 2 — recherche point fixe Nash (avg_b2 = best_response b2) :")
    b1_eq, b2_eq, e_eq, avg_eq = find_fixed_point(start=800)
    print()
    print(f"  >> Équilibre : b1 = {b1_eq}, b2 = {b2_eq}, avg_b2 supposé = {avg_eq:.1f}")
    print(f"     E[profit par trade] = {e_eq:.2f} SeaShells")
    print()

    # ---------- Phase 3 : sensibilité ----------
    print("Phase 3 — top-10 bids robustes autour de l'équilibre :")
    print(f"  (avg_b2 supposé = {b2_eq}) ")
    top = top_k_bids(b2_eq, k=10)
    print(f"  {'rank':>4s}  {'b1':>4s}  {'b2':>4s}  {'E':>8s}  {'gap-vs-best':>12s}")
    best_E = top[0][2]
    for i, (b1, b2, e) in enumerate(top, 1):
        gap = e - best_E
        print(f"  {i:>4d}  {b1:>4d}  {b2:>4d}  {e:>8.3f}  {gap:>+12.3f}")
    print()

    # ---------- Phase 4 : robustesse sous différents avg_b2 ----------
    print("Phase 4 — robustesse : E[profit] pour (b1*, b2*) sous avg_b2 varié :")
    avg_scenarios = (750, 780, 800, 820, 840, 860, 880)
    print(f"  {'b1':>4s}  {'b2':>4s}  " + "  ".join(f"avg={a:>3d}" for a in avg_scenarios))
    # top-5 candidats à stress-tester
    candidates = [(b1, b2) for (b1, b2, _) in top[:5]]
    for b1, b2 in candidates:
        row = f"  {b1:>4d}  {b2:>4d}  "
        for a in avg_scenarios:
            e = expected_profit(b1, b2, a)
            row += f"  {e:>7.2f}"
        print(row)
    print()

    print("=" * 72)
    print(f"RECOMMANDATION : b1 = {b1_eq}, b2 = {b2_eq}  (E[profit/trade] ~ {e_eq:.1f} SS)")
    print("=" * 72)
