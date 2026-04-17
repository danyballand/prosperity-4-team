"""
Optimisation du manual invest R2 : Research / Scale / Speed.

Formule IMC :
  Research(x) = 200_000 * ln(1+x) / ln(101)
  Scale(x)    = 7 * x / 100
  Speed_rank  = 0.1 + 0.8 * f(x) where f depends on rank (unknown → modélisé)

PnL = Research(R) * Scale(S) * Speed_rank(Sp) - 500 * (R + S + Sp)

Contrainte : R + S + Sp <= 100 (pourcentages)
"""
import math

def research(x):
    if x <= 0:
        return 0
    return 200_000 * math.log(1 + x) / math.log(101)

def scale(x):
    return 7 * x / 100

def speed_rank(x, scenario="median"):
    """Modélise le rank Speed selon hypothèse sur la distribution adversaire.
    - pessimistic : beaucoup de joueurs bidden haut en Speed → besoin ≥ 80% pour top
    - median      : distribution gaussienne autour de 30-40%
    - optimistic  : beaucoup de joueurs ignorent Speed → facile d'être en haut
    """
    x = max(0, min(100, x))
    if scenario == "pessimistic":
        # Top rank seulement si >= 80%
        return 0.1 + 0.8 * min(x / 80, 1.0)
    elif scenario == "optimistic":
        # Top rank dès 40%
        return 0.1 + 0.8 * min(x / 40, 1.0)
    else:  # median
        # Top rank dès 60%
        return 0.1 + 0.8 * min(x / 60, 1.0)

def pnl(R, S, Sp, scenario="median"):
    if R + S + Sp > 100:
        return None
    budget_used = 500 * (R + S + Sp)
    return research(R) * scale(S) * speed_rank(Sp, scenario) - budget_used


def grid_search(scenario, step=1):
    best = -1e18
    best_alloc = None
    results = []
    for R in range(0, 101, step):
        for S in range(0, 101 - R, step):
            for Sp in range(0, 101 - R - S, step):
                p = pnl(R, S, Sp, scenario)
                if p is not None:
                    results.append((R, S, Sp, p))
                    if p > best:
                        best = p
                        best_alloc = (R, S, Sp)
    results.sort(key=lambda x: -x[3])
    return best_alloc, best, results[:10]


if __name__ == "__main__":
    print("=" * 70)
    print("OPTIM MANUAL INVEST R2")
    print("=" * 70)
    print("\nFormule PnL = Research(R%) × Scale(S%) × Speed_rank(Sp%) - 500×(R+S+Sp)")
    print("Budget = 50 000 XIREC, R+S+Sp <= 100%\n")

    for scenario in ["optimistic", "median", "pessimistic"]:
        print(f"\n--- Scénario Speed rank = {scenario.upper()} ---")
        best_alloc, best_pnl, top10 = grid_search(scenario, step=1)
        R, S, Sp = best_alloc
        print(f"  OPTIMUM : R={R}%  S={S}%  Sp={Sp}%  (total {R+S+Sp}%)")
        print(f"  Research({R}) = {research(R):>10.1f}")
        print(f"  Scale({S})    = {scale(S):>10.3f}")
        print(f"  Speed({Sp})   = {speed_rank(Sp, scenario):>10.3f}")
        print(f"  Budget used = {500*(R+S+Sp):>10} XIREC")
        print(f"  >>> PnL NET = {best_pnl:>+10.1f} XIREC <<<\n")
        print(f"  Top 10 allocs :")
        for (r, s, sp, p) in top10:
            print(f"    R={r:>3} S={s:>3} Sp={sp:>3}  total={r+s+sp:>3}%  PnL={p:+.0f}")

    # Comparaison de 3 allocations "intéressantes" dans les 3 scénarios
    print("\n" + "=" * 70)
    print("ALLOCATIONS CANDIDATES : PnL selon scénario rank Speed")
    print("=" * 70)
    candidates = [
        (100, 0, 0, "100% Research (no Scale = 0)"),
        (50, 50, 0, "50/50 R-S (Sp=0 → rank bas)"),
        (50, 30, 20, "50/30/20 équilibré"),
        (40, 30, 30, "40/30/30 équilibré"),
        (30, 30, 40, "30/30/40 favor Speed"),
        (33, 33, 34, "tiers égaux"),
        (60, 20, 20, "60/20/20 Research-heavy"),
        (20, 20, 60, "20/20/60 Speed-heavy"),
        (0, 0, 0, "all-zero (baseline no loss)"),
    ]
    print(f"{'Alloc':<32} {'Optimistic':>12} {'Median':>12} {'Pessimistic':>12}")
    for R, S, Sp, desc in candidates:
        p_opt = pnl(R, S, Sp, "optimistic")
        p_med = pnl(R, S, Sp, "median")
        p_pes = pnl(R, S, Sp, "pessimistic")
        print(f"R={R:>2} S={S:>2} Sp={Sp:>2}  {desc:<20} {p_opt:>+12.0f} {p_med:>+12.0f} {p_pes:>+12.0f}")
