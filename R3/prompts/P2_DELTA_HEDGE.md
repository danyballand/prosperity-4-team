# PROMPT CODEX P2 — Delta empirique & corrélation VE ↔ VEVs

## Contexte général (à lire avant de commencer)

Je participe à **IMC Prosperity 4**, challenge de trading algo organisé par IMC Trading. R1 fini rang #366 mondial, R2 similaire. On attaque **Round 3 : format options**.

**Univers R3** :
- 1 produit stable : `HYDROGEL_PACK` (~10,000, MM classique)
- 1 underlying : `VELVETFRUIT_EXTRACT` (VE) — ~5247-5295, spread ~5
- 10 call options européens sur VE : `VEV_{4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500}`
- TTE présumé **7 jours** à t=0 de R3, décroît
- r=0

**Baseline actuel** : trader MM avec **+23,929 sur 3j backtest**, mais uniquement HYD + VE + 4 VEV ITM. Je veux **hedger une position directionnelle en VEV** avec VE pour extraire de l'edge sur les mispricings.

**Ce prompt répond à la question** : si je prends une position longue/courte sur un VEV, combien de VE dois-je trader en opposite pour neutraliser le delta ?

---

## Données disponibles

Dans `R3/data/` j'ai 3 jours d'order book + trades (format détaillé dans P1).

**Format CSV `prices_round_3_day_*.csv` (sep `;`)** :
```
day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss
```

**Format `trades_round_3_day_*.csv`** :
```
timestamp;symbol;price;quantity;buyer;seller
```

---

## Ta mission : delta empirique + lead/lag + stabilité du hedge

### Tâche 1 — Delta réalisé par strike

Pour chaque strike K, sur chaque jour :

1. Construire la série `S_t = mid_price(VE_at_t)` (1 sample par ts=100)
2. Construire la série `C_t = mid_price(VEV_K_at_t)`
3. Calculer les **returns** : `dS_t = S_t - S_{t-1}`, `dC_t = C_t - C_{t-1}`
4. **Régresser** `dC_t = β * dS_t + ε_t` → **β = delta empirique**
5. Comparer à **delta BS théorique** calculé avec l'IV moyenne du jour (formule : `N(d1)` pour un call)

Produire une table :
```
day, strike, delta_empirical, delta_BS_theoretical, diff, R², n_obs
```

### Tâche 2 — Lead / lag VE ↔ VEV

**Hypothèse** : si les VEVs bougent AVANT VE, ça veut dire que les options traders sont informés (insider flow). Si VE leade, c'est normal (l'underlying leade).

Pour chaque strike K :

1. Calculer la **cross-correlation** entre `dS_t` et `dC_{t+k}` pour k ∈ {-10, ..., 10}
2. Identifier le **lag optimal** où la corrélation pic
3. Si le lag est **négatif** (VEV leade VE) → **signal de flux informé** sur ce strike → opportunité directionnelle
4. Si le lag est **0 ou positif** (VE leade) → hedge direct possible sans signal

Livrables :
- Table par strike : `lag_optimal, corr_at_lag, corr_at_0, interpretation`
- Graphe : cross-corr function par strike (10 subplots)

### Tâche 3 — Stabilité du hedge dans le temps

Le delta n'est pas constant — il dépend de S et de TTE. Tester si le **hedge** est stable ou gamma-driven.

1. Rolling regression sur fenêtres de 200 ts : `delta_t = β_window(dC | dS)`
2. Tracer delta rolling par strike sur les 3 jours
3. Calculer **std(delta_rolling)** par strike → plus c'est haut, plus le hedge est fragile
4. Identifier les **régimes de gamma** (moments où le delta swing fort, ex: proche ATM quand S s'approche de K)

### Tâche 4 — Hedge ratio recommandé + coût d'exécution

Pour une position longue de 50 VEV_K, calculer :

1. Nombre de VE à short = `50 * delta_empirical` (arrondi entier)
2. **Coût d'exécution** = half-spread VE × |short_qty| + half-spread VEV × 50
3. **Coût de rebalancing** : si delta swing à 0.1 par 10 ts, combien de VE doit-on re-trader ?
4. **PnL net attendu** d'un trade long VEV + hedge si IV revient à la surface (utiliser résultats P1 si disponibles, sinon assume edge 1 tick)

Produire un classement strike → edge net après hedge.

### Tâche 5 — Cross-VEV hedging

Un hedge n'est pas forcément fait avec VE. On peut hedger VEV_5400 avec VEV_5300 (delta similaire, coût plus faible peut-être).

1. Calculer **corrélation pairwise** entre tous les VEVs
2. Identifier des paires où corr > 0.95 → hedge intra-options possible
3. Calculer le "residual" d'une telle paire (spread) et tester si mean-reverting

---

## Format du livrable

1. **Script Python** reproductible (<3 min run)
2. **CSV** `delta_empirical.csv` avec colonnes : `day, strike, delta_emp, delta_BS, diff, R², n_obs`
3. **Graphes PNG** :
   - (a) delta empirique vs BS par strike (scatter)
   - (b) cross-corr functions VE-VEV_K par strike
   - (c) delta rolling par strike (3 jours)
   - (d) correlation matrix VEV × VEV
4. **Résumé texte** (~400 mots) :
   - Quels strikes sont OK à hedger avec VE (delta stable, lag 0)
   - Quels strikes ont **informed flow** (VEV leade VE) → signal tradable
   - Recommandation de hedge ratio par strike avec coût chiffré

---

## Notes techniques

- Position limits : VE=200, VEV variable 50-200. Une position 50 VEV × delta 0.8 = 40 VE à short → faisable.
- Attention : les spreads sont en ticks entiers, pas en fractions. Arrondir les hedges.
- Si trop peu de trades sur un strike (V6000/V6500 sont illiquides), signale-le.

---

## Quelle question prioritaire ?

Si tu ne réponds qu'à **une seule** chose : **quels strikes ont un hedge VE stable ET un signal directionnel exploitable (lead/lag ou IV mispricing) ?**
