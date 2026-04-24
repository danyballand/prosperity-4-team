# PROMPT CODEX P4 — Spreads, baskets & stat arb multi-produits

## Contexte général (à lire avant de commencer)

**IMC Prosperity 4**, challenge de trading algo. R1 rang #366 mondial, R2 similaire. On attaque **R3 : trading d'options**.

**Univers R3** :
- `HYDROGEL_PACK` — stable ~10,000
- `VELVETFRUIT_EXTRACT` (VE) — ~5247-5295, underlying des options
- 10 calls européens `VEV_{4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500}` sur VE
- TTE ~7 jours à t=0, r=0

**Baseline** : MM passif **+23,929 sur 3j backtest**. Je veux **exploiter des violations d'arbitrage statistique** entre les strikes, entre les produits, pour du PnL quasi-sans-risque (convergence forcée par l'absence d'arbitrage théorique).

**Précédent succès** : en R2, on avait Osmium et Pepper, et on avait trouvé une corrélation exploitable **bidirectionnelle** entre les 2 produits. On n'a pas totalement exploité ça (décalage temporel). Ici il y a 12 produits → potentiellement beaucoup plus de paires.

---

## Données disponibles

3 jours dans `R3/data/` :

**`prices_round_3_day_*.csv`** (sep `;`) :
```
day;timestamp;product;bid_price_1..3;bid_volume_1..3;ask_price_1..3;ask_volume_1..3;mid_price;profit_and_loss
```

**`trades_round_3_day_*.csv`** (sep `;`) : trades exécutés publics

---

## Ta mission : trouver tous les arbitrages statistiques exploitables

### Tâche 1 — Vertical spreads (butterfly / bull / bear)

**Principe théorique** : pour deux calls sur le même underlying, deux strikes K1 < K2 :
- `C(K1) >= C(K2)` (le call avec le strike plus bas vaut plus)
- `C(K1) - C(K2) <= K2 - K1` (différence de strikes)
- `(C(K1) - C(K2)) / (K2 - K1)` doit être entre 0 et 1

**Butterfly** : `C(K-Δ) - 2*C(K) + C(K+Δ) >= 0` **toujours** (convexité).

Pour chaque triplet {K1, K2, K3} adjacent (e.g. {5000, 5100, 5200}, {5100, 5200, 5300}, ...) :

1. Calculer à chaque ts : `fly_t = C(K1) - 2*C(K2) + C(K3)` (avec mid_prices)
2. **Vérifier** que `fly_t >= 0` toujours. Si violations → **arbitrage pur** (acheter le fly quand négatif)
3. Calculer **stats du fly** : mean, std, min, max par jour
4. Mean-reversion du fly : autocorr, half-life
5. EV d'une stratégie "long fly quand Z < -2, close quand Z > 0" en tenant compte du triple half-spread

Produire une table :
```
K1, K2, K3, day, violations_count, mean_fly, std_fly, half_life, EV_trade_estimated
```

### Tâche 2 — Put-call parity ou put-put spreads

**⚠️ Important** : nos 10 VEVs sont TOUS des calls (à priori). Pas de puts listés. **Confirme-le** en regardant les prix (un put aurait un prix qui monte quand S baisse).

Si par chance il y avait des puts cachés dans la nomenclature → parity C - P = S - K*exp(-rT) devient exploitable.

Sinon, passe à la tâche suivante.

### Tâche 3 — Calendar spreads (si applicable)

**Problème** : tous nos VEVs ont le MÊME expiry (présumé J+7 à t=0). Pas de calendar spread au sens strict.

**Mais** : le **decay theta** devrait faire baisser les VEVs ATM/OTM au fil des 3 jours. Mesurer :

1. Pour chaque strike, `mid_price_day_N - mid_price_day_{N-1}` (fin de jour à fin de jour)
2. Comparer à **theta théorique BS** (avec IV estimée en P1)
3. Si decay réalisé > theta BS → VEVs sur-dépréciés → long opportunity
4. Si decay réalisé < theta BS → VEVs sous-dépréciés → short opportunity

### Tâche 4 — Pair trade HYD ↔ autre chose

HYD est stable ~10000. A priori indépendant de VE. Mais vérifier :

1. Corrélation HYD ↔ VE
2. Corrélation HYD ↔ chaque VEV
3. Si corrélation > 0.3 sur un ts court (event-driven) → pair trade possible
4. Si corrélation ~0 → HYD est un vrai stand-alone (OK, on le trade seul)

### Tâche 5 — Synthetic replication

On peut recréer VE synthétiquement avec une combinaison de VEVs (couverture delta complète) :
- Long VEV_4000 + short VEV_5000 ≈ long VE exposure sur la tranche [4000, 5000]

1. Pour chaque VEV, calculer le **delta** (cf P2 ou BS)
2. Construire le portefeuille `sum(w_K * VEV_K) ≈ VE`
3. Comparer le prix synthétique à VE. Si écart > coût exec → arb pur

### Tâche 6 — Stat arb cross-strike par co-intégration

Tester **co-intégration** (Johansen ou Engle-Granger) sur les paires de VEVs :

1. Pour chaque paire (K1, K2), tester la stationarité du résidu `C(K1) - β * C(K2)`
2. Si stationnaire à 95% → paire co-intégrée → trade mean reversion
3. Classer les paires par **Sharpe attendu** = (mean|residu| / std) × (edge/cout)

### Tâche 7 — Synthèse classements

Prends TOUS les arbs trouvés (tâches 1-6) et fais un classement unique par :
- **EV_par_trade** (en ticks nets)
- **Fréquence des opportunités** (nombre de trades/jour)
- **Capital requis** (position sizing)
- **Risque max** (worst-case drawdown)

Top 5 recommandations actionnables.

---

## Format du livrable

1. **Script Python** (<5 min run)
2. **CSV** `arb_opportunities.csv` : une ligne par opportunité trouvée
3. **Graphes PNG** :
   - (a) Fly t-series par triplet
   - (b) Correlation matrix 12×12 produits
   - (c) Synthetic VE vs VE réel (trace)
   - (d) Co-integration p-values matrix
4. **Rapport markdown** : top 5 arbs avec code pseudo-python pour chacun

---

## Notes techniques

- Attention au **bid-ask bounce** : les violations de butterfly peuvent être artefact de mid calculé sur des books fins. Vérifier avec les **tradable prices** (bid pour vendre, ask pour acheter).
- Position limits : HYD=80, VE=200, VEV 50-200. Une stratégie qui demande 500 VEV est infaisable.
- **Coût par trade** : half-spread × 2 (entry + exit). Pour VE spread=5 → 2.5 tick × 2 = 5 ticks. Pour VEVs variable 1-5 ticks.
- Les Z-scores et tests de co-intégration doivent être **robustes aux jumps** (une fenêtre de 3 jours c'est court, attention overfitting).

---

## Questions prioritaires

Si tu ne réponds qu'à **ces 3 choses** :

1. **Existe-t-il des violations de butterfly persistantes** (arbitrage pur) sur un ou plusieurs triplets ?
2. **Quelle paire de VEVs est la plus co-intégrée** et avec quel EV/trade en ticks nets ?
3. **Peut-on répliquer VE synthétiquement** avec des VEVs et battre le spread VE direct ?
