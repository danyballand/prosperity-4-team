# Gemini Deep Research — IMC Prosperity Round 2 : BASKET / ETF ARBITRAGE (précédent P3 2025)

## Rôle et niveau d'exigence

Tu es un quant ETF-arb / index-arb senior + research analyst. Mission de
**compétitive intelligence exhaustive** sur le format **basket arbitrage**
apparu en Round 2 de Prosperity 3 (2025) avec **PICNIC_BASKET = 6 CROISSANTS +
3 JAMS + 1 DJEMBE**, et qui peut réapparaître sous une autre forme en
Prosperity 4 R2 (avril 2026).

Je veux que tu explores **au minimum 10 repos GitHub** de participants
Prosperity 3 (pas juste les 5 stars), que tu **lises le code Python réel** des
traders.py Round 2, et que tu extraies les **paramètres exacts** (Linear Utility,
Chrispyroberts, Sylvain-Topeza), les **variantes testées et rejetées**, et le
débat **hardcoded mean vs rolling mean** qui a décidé le classement.

## Ma situation précise

### La compétition en cours
- **Édition actuelle** : IMC Prosperity 4 (avril 2026)
- **R1 soumis** : +12,157.69 XIREC, gap ~3k sous top
- **R2 imminent**
- **Mon hypothèse cible pour ce rapport** : si R2 2026 est un basket (format P3 2025), j'ai besoin des params exacts + preuve chiffrée que hardcoded mean bat rolling mean + gestion multi-leg position limit

### Ce que j'ai déjà préparé (à ne PAS redupliquer)

Dans `R2/r2_primitives.py` j'ai :
- `HardcodedMeanZ(mean, std_window)` : Z-score avec mean **hardcodé** (approche Linear Utility P2 winners)
- `BasketPricer` : prix synthétique d'un basket
- `multi_leg_orders`, `net_delta`, `suggest_hedge`, `safe_order`

Dans `R2/trader_r2_template.py` j'ai une config `BASKET_CONFIG` :
```python
BASKET_CONFIG = {
    'enabled': False,
    'basket': 'PICNIC_BASKET',
    'components': {'CROISSANTS': 6, 'JAMS': 3, 'DJEMBE': 1},
    'mean_hardcoded': 379.50439988484239,  # Linear Utility P2 (à RE-calibrer en P4)
    'std_window': 45,
    'zscore_threshold': 7,
    'target_position': 58,  # jamais 100% du limit
    ...
}
```

Dans le handoff j'ai noté les params connus :
- **Linear Utility** (P2 R2 rank 2 basket) : mean hardcodé 379.50..., window 45, z=7, target 58/60
- **Chrispyroberts** (P3 7th basket) : z=20, allocation multi-basket 100/60/32/8%

Ce que je n'ai PAS et que je veux de toi : les params de **10+ autres teams P3 2025
basket**, le détail du débat **hardcoded vs rolling** chiffré, la gestion des
**position limits multi-legs** (si basket = 6C+3J+1D et tu tiens +10 baskets,
tu as +60C +30J +10D — comment ils clampent quand un leg bouche ?), et les
**variantes de basket** (PICNIC_BASKET1 vs PICNIC_BASKET2, overlap ou non ?).

## Mission pour toi

### Partie 1 — Mécanique PICNIC_BASKET P3 2025

Reconstruis la mécanique complète :

1. **Composition** : PICNIC_BASKET1 = 6C + 3J + 1D. Existait-il PICNIC_BASKET2 ?
   Avec quels composants ? Overlap avec BASKET1 ?
2. **Position limits** : par composant et par basket
3. **Matching** : pro-rata ou LOB FIFO ?
4. **Spread théorique** : `basket_mid - (6*C_mid + 3*J_mid + 1*D_mid)`
   ou est-ce que les tops utilisent `swmid` (size-weighted mid) ?
5. **Dimensions du dataset** : 3 jours CSV, 1000 snapshots/jour, 100k ticks/jour ?

### Partie 2 — Exploration GitHub exhaustive (min 10 repos P3 2025)

Pour chaque repo R2 :

1. **Identification** : team, rang final P3, score R2 si dispo, lien `trader.py` R2
2. **Formule spread** : exact (basket_mid vs synthétique + weights)
3. **Mean** :
   - **Hardcoded** → valeur exacte (à 5+ décimales si possible)
   - **Rolling** → window size (en ticks)
   - Si ils ont switché pendant la compétition → extrait des commits
4. **Std** : window, EWMA decay, ou fixed
5. **Z-threshold** : `entry_z`, `exit_z`, `stop_z`
6. **Target position** : quel % du limit ils visent ? (Linear Utility vise 58/60 = 96.6%)
7. **Gestion multi-leg** : quand un leg est saturé, ils réduisent la qty totale ou ils skip ?
8. **Double basket** : si PICNIC_BASKET2 existait, l'ont-ils tradé ? Arbitrage inter-basket ?
9. **Allocation multi-signal** : Chrispyroberts a 100%/60%/32%/8% — explique la logique
10. **Extrait de code** (15-25 lignes) du cœur de la logique basket

### Partie 3 — Tableau comparatif (min 15 lignes)

Colonnes :
- Team / rang P3 / score R2
- Mean (hardcoded value OR rolling window)
- Std window
- entry_z / exit_z
- Target position (% of limit)
- Spread formula (swmid or naive mid)
- Multi-basket strategy
- Leg rebalance rule
- Notable tricks

### Partie 4 — Le débat **hardcoded vs rolling** chiffré

C'est la partie la plus importante pour moi.

- Donne-moi **≥ 3 preuves chiffrées** que hardcoded mean bat rolling mean sur R2
- Teams qui ont utilisé rolling mean : leur rang final / score R2
- Teams qui ont utilisé hardcoded : leur rang final / score R2
- Y a-t-il un top team qui a utilisé rolling mean et gagné quand même ? Comment ?
- **Threshold de window size** : en dessous de combien de ticks rolling mean converge vers prix courant → z-score étouffé → 0 trade ?

### Partie 5 — Variantes testées et REJETÉES

Depuis les historiques git :
- Weights alternatifs (5C+3J+1D, 6C+4J+1D, …) : combien de XIREC perdus
- Z-thresholds essayés : 1, 2, 3, 5, 10, 20 → plateau ou pic ?
- Exit rules complexes (trailing stop, time exit) → résultat
- Régression OLS des weights vs hardcodage manuel → préférence des tops
- Ajout de features (volume, imbalance) au spread → gain ou perte ?

### Partie 6 — Gestion multi-leg position limit

Si target_position_basket = 58 et basket = 6C+3J+1D :
- C : 58 * 6 = 348 unités théoriques, mais limit C typiquement 250
- J : 58 * 3 = 174, limit probably 350 (OK)
- D : 58 * 1 = 58, limit probably 60 (OK)

Donc le leg **saturant** est C. Comment les tops gèrent ?
- Clamp target_basket à `min(limit_basket, limit_C / 6, limit_J / 3, limit_D / 1)` ?
- Rotation dynamique (trade basket 1 quand C saturé puis basket 2) ?
- Hedge delta-neutral partiel ?

**Donne-moi la formule exacte utilisée par Linear Utility et Chrispyroberts.**

### Partie 7 — Post-mortems et erreurs fatales

- Teams top-R1 qui se sont cassés R2 basket : pourquoi ?
- Erreurs de position limit (somme ordres > limit → rejet total, cas CarterT27 P3)
- Erreurs de signe (weights inversés)
- Rolling mean + window trop long → pas de signal
- Rolling mean + window trop court → z-score oscille, overtrade

### Partie 8 — Diagnostic de MA config par défaut

Compare mon `BASKET_CONFIG` aux tops :
- `mean_hardcoded = 379.50...` : c'est la valeur **P2 Linear Utility** (basket
  P2 différent, 4C+6S+1R). **Elle ne s'applique PAS directement à P4 2026**.
  Dis-moi comment je dois recalibrer sur les 3 jours CSV R2 2026 le jour J.
- `std_window = 45` : c'est Linear Utility. Les autres tops sont-ils aussi à 45 ?
- `zscore_threshold = 7` vs Chrispyroberts 20 : quel est le bon range à grid-searcher ?
- `target_position = 58` sur limit 60 : la règle « jamais 100% » est-elle confirmée ?

### Partie 9 — Playbook 60 min jour J

Si R2 2026 s'avère être un basket :
1. 3 signaux CSV qui confirment (corrélation basket/composants > 0.95, r² combo > 0.9)
2. Script de **calibration automatique du mean** sur les 3 jours CSV (3 lignes à coller)
3. Params de départ par défaut (valeurs exactes) + range grid search
4. Les 3 pièges à vérifier (multi-leg limit, signe weights, window pas trop long)
5. Les 2 A/B tests obligatoires avant submit

## Format livrable

```
# Compétitive Intelligence — Basket Arb R2 (P3 2025 → P4 2026)

## 1. Mécanique PICNIC_BASKET P3 2025
## 2. Repos P3 2025 explorés (min 10)
## 3. Tableau comparatif (min 15 lignes)
## 4. Hardcoded vs Rolling mean : preuves chiffrées
## 5. Variantes testées et rejetées
## 6. Gestion multi-leg position limit
## 7. Post-mortems
## 8. Diagnostic de ma config
## 9. Playbook jour J (60 min)
## 10. Sources complètes
```

## Points d'attention

- **⚠ Correction connue** : GIFT_BASKET (4C+6S+1R) = **P2 R3**, **PAS** P2 R2
  ni P3 R2. P3 R2 = PICNIC_BASKET (6C+3J+1D). **Reste sur P3 R2.**

- **Linear Utility ≠ P3** : Linear Utility est P2 #2 (2024), leur hardcoded mean
  379.50... concerne le basket P2 **R3** (GIFT). Pour le rapport P3 R2, je veux
  les params **des tops P3 2025** spécifiquement, pas projetés depuis P2.

- **Code réel > README**, citation fichier+ligne, dire « non trouvé » plutôt qu'inventer.

- **Preuves chiffrées obligatoires** pour tout claim de type « X bat Y ».

## Repos P3 2025 à démarrer

- https://github.com/chrispyroberts/imc-prosperity-3 (#7 global)
- https://github.com/Sylvain-Topeza/imc-prosperity-3 (top 1%)
- https://github.com/CarterT27/imc-prosperity-3 (#9, post-mortem position limit)
- Cherche "imc-prosperity-3" + "PICNIC_BASKET" sur GitHub

---

**Priorité : preuves chiffrées hardcoded vs rolling + formule exacte multi-leg clamp.**
