# PROMPT CODEX P3 — Market microstructure & informed flow

## Contexte général (à lire avant de commencer)

**IMC Prosperity 4**, challenge de trading algo. Équipe R1 rang #366, R2 similaire. On attaque **Round 3 : trading d'options**.

**Univers R3 (12 produits)** :
- `HYDROGEL_PACK` — stable ~10,000, spread ~16
- `VELVETFRUIT_EXTRACT` (VE) — ~5247-5295, spread ~5, underlying des options
- 10 calls `VEV_{4000...6500}` strike variable, TTE ~7 jours

**Baseline** : trader MM **+23,929 sur 3j backtest**. Stratégie : pennying, triple_edge, inventory_clearing, fair-value Kalman. Je veux maintenant comprendre **QUI trade dans ce marché** et **QUAND est-il dangereux de quoter**.

**Historique pertinent (R1/R2)** : on avait détecté un side channel bizarre en R2 (+1,011 PnL sur Osmium juste en ajoutant un hook `id_markout=True` sans logique apparente — a priori effet reproductible via tick rate / timing). On veut savoir si R3 a des patterns similaires.

---

## Données disponibles

3 jours dans `R3/data/` :

**`prices_round_3_day_*.csv`** (sep `;`) :
```
day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss
```

**`trades_round_3_day_*.csv`** (sep `;`) — trades exécutés **publics** (ne sont PAS nos trades) :
```
timestamp;symbol;price;quantity;buyer;seller
```

**⚠️ Les champs `buyer` et `seller` contiennent des IDs** (parfois vides, parfois pseudonymes). Sur R1 on a identifié "Ruby", "Pengo" comme traders récurrents. En R3 les IDs sont potentiellement différents.

---

## Ta mission : cartographier l'écosystème de traders et identifier les dangers

### Tâche 1 — Distribution des trade sizes par produit

Pour chaque produit (12) :

1. **Histogramme** des `|quantity|` des trades publics (1 bin par taille entière)
2. Calculer **median, mean, P95, max**
3. Identifier les "gros trades" (P95+ ou Z>2) — **sont-ils suivis d'un move de prix dans les N ticks suivants ?**
   - Markout 100 ts, 500 ts, 1000 ts après un gros trade
   - Si markout positif quand acheté / négatif quand vendu → **gros trades = informed**
4. Classer les produits par **"danger level"** (plus les gros trades ont markout net, plus c'est dangereux de quoter contre)

### Tâche 2 — Patterns temporels

1. Volume trade par **tranche de ts** (bins de 10,000 ts) pour chaque produit
2. Moments "chauds" (pics de volume) = attention à l'adverse selection
3. Moments "calmes" = on peut quoter plus large sans risque
4. Heures corrélées entre produits ? (si HYD explose en volume au même ts que VE → event systémique)

### Tâche 3 — Order Book Imbalance (OBI) prédictif

Pour chaque produit :

1. Calculer `OBI = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol)` à chaque ts
2. Segmenter en quintiles (Q1 = OBI très négatif, Q5 = très positif)
3. Pour chaque quintile, mesurer **mid-price change** sur les 100-500 ts suivants
4. Si Q5 - Q1 > 2 ticks → OBI prédictif → peut skewer les quotes
5. Comparer les produits : lequel a l'OBI le plus informatif ?

### Tâche 4 — Identification traders (buyer/seller IDs)

1. Lister tous les **buyer IDs** uniques et tous les **seller IDs** uniques
2. Pour chaque ID :
   - Nombre de trades totaux
   - Taille moyenne
   - Produits tradés (concentré sur 1 ou diversifié ?)
   - **PnL implicite** si on suppose qu'ils achètent/vendent à leur prix et se retournent au mid 500 ts plus tard
3. Identifier le **top 3 des traders les plus profitables** (ceux qui extraient de l'edge) → ce sont les informed
4. Identifier les **traders losers** (ceux qu'on peut imiter ou qu'on peut profiter de leurs pertes)
5. **Side channel alert** : y a-t-il un ID qui n'apparaît QUE dans des conditions spécifiques (début de jour, juste avant un gros move) ?

### Tâche 5 — Wall dynamics

Les "walls" (gros volumes à un prix donné) sont souvent la cible des informed.

1. Pour chaque produit, identifier les walls (level avec vol > P90 du produit)
2. Suivre **la durée de vie** d'un wall (combien de ts avant qu'il soit éliminé/baissé)
3. **Quand un wall est hit**, que fait le prix dans les 100 ts qui suivent ?
   - Si move DANS la direction du hit = flow informed
   - Si move contre = flow bruité, opportunité MM

### Tâche 6 — Côté asymétrique par produit

Certains produits peuvent avoir du flow asymétrique (e.g. plus de sellers que buyers sur les options OTM chères = décroissance systémique).

Pour chaque produit :
1. Ratio `nombre_buy_trades / nombre_sell_trades`
2. Ratio `volume_acheté / volume_vendu`
3. Si asymétrie forte → prévoir un skew structurel dans nos quotes

---

## Format du livrable

1. **Script Python** reproductible
2. **Rapport markdown** structuré avec :
   - Table "danger level" par produit
   - Top 5 traders identifiés (IDs + stats)
   - Heatmap temporelle (volume par produit × ts)
   - Recommandations concrètes MM par produit : edge min, skew OBI, éviter telle heure, etc.
3. **Graphes PNG** : histogrammes sizes, heatmap temps, OBI predictivity per produit

---

## Questions prioritaires

Si tu dois ne répondre qu'à **3 choses** :

1. **Quels produits sont dangereux** (haute adverse selection) → élargir nos edges
2. **Y a-t-il un side channel trader** identifiable (ID unique avec edge) qu'on peut suivre / imiter / front-run
3. **Quelle fenêtre temporelle** du jour est la plus profitable pour faire MM (et laquelle éviter)
