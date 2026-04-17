# R1 / rejected — stratégies testées qui n'ont PAS marché

**Objectif de ce dossier** : garder trace de tout ce qu'on a essayé pendant R1
pour ne pas refaire les mêmes erreurs. Chaque fichier ici est un essai
documenté qui a été **rejeté sur base de backtest chiffré**.

Si tu as une idée brillante pour R2+, **check d'abord ce dossier** — il y a
de grandes chances qu'on l'ait déjà testé.

---

## Récapitulatif rapide

| Fichier | Type | Résultat backtest 3j | Verdict |
|---|---|---:|---|
| `trader_stoikov.py` | Avellaneda-Stoikov market making full | **+84** | Catastrophique vs v31 (+27,653) |
| `trader_stoikov_v2.py` | Stoikov avec drift_horizon=5 ticks | **+12,015** | Moitié de v31, rejeté |
| `trader_pep_bnh.py` | Pure buy-and-hold Pepper | **-4,367** | Perte massive |
| `trader_signal_stack.py` | 5 signaux empilés en TAKE-only | **-166,874** | Désastre (friction x100) |
| `local_backtest.py` | Backtester v1 | biaisé | Fuite causale (B1) |
| `local_backtest_v2.py` | Backtester v2 | biaisé | Book pas mute (B2) |
| `retest_with_v2.py` | Harness A/B v2 | N/A | Remplacé par retest_with_v3 |

---

## 1. `trader_stoikov.py` — Avellaneda-Stoikov full

**Hypothèse** : la formule académique de market making (Stoikov 2008) avec
reservation price + optimal spread devrait outperformer les heuristiques.

**Formule implémentée** :
```
reservation_price = mid - q * γ * σ² * (T - t)
optimal_spread   = γ * σ² * (T - t) + (2/γ) * ln(1 + γ/κ)
bid = reservation_price - optimal_spread / 2
ask = reservation_price + optimal_spread / 2
```

**Pourquoi ça a foiré** :
- Avec `T - t = 100_000` ticks, le terme `q * γ * σ² * (T - t)` devient
  **énorme** (dérive de +50,000 ticks sur le prix de référence). La reservation
  price s'envole hors du book, nos quotes ne matchent jamais.
- Le paramètre `γ` (risk aversion) n'a pas de calibration évidente. Essayé
  γ ∈ {0.01, 0.05, 0.1, 0.5, 1.0} → tous foirent.

**Résultat** : **+84 XIREC** sur 3 jours vs +27,653 pour v31.

**Leçon** : formule académique ≠ formule qui marche sur un marché discret avec
position limits et latency. Stoikov marche en continuous-time avec grosse
liquidité, pas dans le setup Prosperity.

---

## 2. `trader_stoikov_v2.py` — Stoikov avec drift_horizon fixé

**Hypothèse** : si le problème de v1 était le T-t énorme, limiter l'horizon
à 5 ticks devrait normaliser le terme de dérive.

**Modification** : `drift_term = q * γ * σ² * min(5, T - t)`

**Pourquoi ça a échoué** :
- Ça a fixé le problème du drift mais la formule reste fragile face aux
  cliffs paramétriques observés sur Osm (make_edge=97 sur cliff).
- Le `optimal_spread` de Stoikov donne des valeurs ~20-30 ticks sur Osm,
  alors que le vrai optimum empirique est 97. Écart énorme.

**Résultat** : **+12,015 XIREC** = 43% de v31 = catastrophe.

**Leçon** : l'edge optimal sur Osmium est **exogène** (dépend du flow bot
invisible, pas de la volatilité du mid). Stoikov ne peut pas le deviner.

---

## 3. `trader_pep_bnh.py` — Pure buy & hold Pepper

**Hypothèse** : Pepper drift +1000/jour. En achetant +80 au tick 0 et en
tenant jusqu'au dernier tick, on capture 80 × 1000 = 80,000 XIREC théoriques.

**Pourquoi ça a échoué** :
- Le TAKE des 80 units initiaux paie **énormément de spread** (~12 ticks ×
  80 = 960 XIREC de coût immédiat).
- Sans market making en parallèle, **aucun revenu passif** pour compenser.
- La volatilité réalisée fait drawdown intraday → clearing par le match
  engine (pas de vrai P&L final si on tient, mais dans Prosperity la position
  finale est liquidée au mid du dernier tick).

**Résultat** : **-4,367 XIREC** sur 3 jours.

**Leçon** : le bootstrap_entry de v31 (+80 avec cap_offset=9) est déjà
l'optimum — il combine "accumuler long" + "ne pas payer trop de spread".
Un simple buy&hold naïf perd.

---

## 4. `trader_signal_stack.py` — 5 signaux empilés en TAKE

**Hypothèse** : combiner 5 signaux (OBI, momentum, mean-reversion, flow imbalance,
volatility break) chacun → position cible. Prendre la somme pondérée, TAKE
agressif pour matcher la cible à chaque tick.

**Pourquoi ça a échoué catastrophiquement** :
- Chaque TAKE paie 1 tick de spread minimum. Avec 5 signaux qui se
  contredisent, on fait **100-200 TAKEs par jour** → friction énorme.
- Même si les signaux ont un edge moyen de +0.5 ticks, la friction (1 tick
  par trade) les mange complètement.
- Pas de MAKE → jamais de revenu passif.

**Résultat** : **-166,874 XIREC** sur 3 jours (catastrophe).

**Leçon** : **la friction est reine** dans Prosperity. Un signal avec edge
théorique de +X ticks doit être combiné avec du market making passif pour
payer le coût de l'inventaire. TAKE-only ne peut pas scaler.

---

## 5. Pourquoi les backtesters v1 et v2 sont dans `rejected/`

### `local_backtest.py` (v1)

**Bug B1 — Fuite causale** : le backtester utilisait `state.market_trades[ts]`
**à la fois** comme signal ET comme source de fill passif pour nos orders
postés au même tick. Résultat : look-ahead bias massif. Pepper backtest
affichait **105% du live** (impossible — un backtest fidèle ne peut pas
dépasser le live).

### `local_backtest_v2.py` (v2)

**Bug B2 — Book pas décrémenté** : quand on postait 2 ordres sur le même
niveau de prix (ex : 2 × +5 units au bid 9995), le backtester donnait 10
units à chaque ordre → fill de 10 au lieu de 5. Overfill factor 2x.

**v3** a corrigé ces 2 bugs + 2 autres (cutoff off-by-one, sweep cascade).
Voir `../local_backtest_v3.py` et le README du dossier R1.

---

## 6. Stratégies testées mais non-implementées en fichier séparé

Dans `retest_with_v3.py` (un seul fichier au lieu de N variantes) :

| Variante | Delta vs baseline | Rejet |
|---|---:|---|
| adaptive_fixed_fv Osm | -2,100 | Overfit sur Osm day-specific |
| obi_skew Osm 0.5 | -450 | Signal pas directionnel |
| pepper_bayes (AR(1)) | ~0 | Neutre (blend 0-0.75), pire (blend 1) |
| pepper_no_microprice | -320 | Microprice utile pour Kalman |
| friend_weights Osm [40,30,30] | -180 | Distribution déjà optimale à [55,30,15] |
| friend_shadow_join | -240 | Rejoindre le book à thin top = adverse selection |
| asymmetric_clearing | -160 | Symétrie optimale |
| take_only_short | -1,100 | Long bias Osm nécessaire |
| trend_guard_hold_30 | -190 | Trend guard actuel déjà optimal |
| max_bias 40 | -85 | Plus long ≠ plus rentable (cap de +80 atteint) |
| max_bias 50 | -240 | Idem, overshoot |
| bootstrap_offset 15 | -1,230 | Achat trop haut, Pep chute parfois initialement |
| bootstrap_offset 20 | -2,450 | Encore pire |
| bootstrap_offset 30 | -4,180 | Catastrophe |

**Conclusion** : v31 est à son **optimum paramétrique local**. Aucune perturbation
simple n'améliore. C'est pourquoi on est passé à des add-ons structurels (OFI)
plutôt que du tuning pour v32.

---

## 7. Ce qu'on n'a PAS testé et qu'on pourrait retenter plus tard

Liste des idées restantes, classées par priorité estimée pour R1 (à ignorer
sauf énorme justification) :

1. **Micro-arbitrage intra-tick** : si une trade CSV à prix X arrive juste
   avant notre quote à X-1, on devrait nous fille immédiatement. Pas
   vraiment faisable vu la granularité tick=100.
2. **Adaptive make_edge par régime** : edge=50 en basse vol, edge=97 en
   haute vol. Risqué : comment détecter le régime sans overfit ?
3. **Rejoindre le book en fat spread** : quand spread Osm > 30 ticks,
   quoter plus agressif. Non testé mais improbable d'améliorer vu la
   fidélité Osm 41%.

**Règle** : avant de retenter une idée, vérifier d'abord qu'elle n'est pas
couverte implicitement par v31 (triple_edge, pennying, inventory_clearing).

---

## Fin

**Principe** : ce dossier doit grandir à chaque rejected variante. Ajoute
systématiquement ton échec ici avec le pourquoi — ça protège l'équipe de
refaire la même erreur.
