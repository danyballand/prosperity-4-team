# PROMPT CODEX P1 — Surface IV & mispricings VEV

## Contexte général (à lire avant de commencer)

Je participe à **IMC Prosperity 4**, un challenge de trading algorithmique organisé par IMC Trading. Équipe de 2, je suis lead dev. On a fini Round 1 rang #366 mondial, Round 2 rang similaire. On attaque Round 3.

**Le challenge de R3** : le format passe au **trading d'options**. L'univers :
- 1 produit stable : `HYDROGEL_PACK` (mean-reverting ~10000, spread ~16)
- 1 underlying : `VELVETFRUIT_EXTRACT` (VE) — prix ~5247-5295, spread serré ~5
- 10 call options européens sur VE : `VEV_4000, VEV_4500, VEV_5000, VEV_5100, VEV_5200, VEV_5300, VEV_5400, VEV_5500, VEV_6000, VEV_6500`

**TTE (Time To Expiry)** : présumé **7 jours** au début de R3 (à confirmer par toi si possible via les prix).

**Taux sans risque** : présumé 0 (Archipelago Prosperity n'a pas de yield curve).

**Baseline actuel** : j'ai un trader MM passif qui fait **+23,929 sur 3 jours de backtest** en tradant uniquement HYD + VE + VEV_4000/4500/5000/5100. Les VEV_5200-6500 sont désactivés car j'ai pas de pricing options (ils saignaient -11k en v1). C'est ce prompt qui va débloquer ce manque.

---

## Données disponibles

Dans `R3/data/` j'ai **3 jours de snapshots de l'order book** à résolution timestamp=100 :

- `prices_round_3_day_0.csv` — 120k lignes, ts 0→999,900
- `prices_round_3_day_1.csv` — idem
- `prices_round_3_day_2.csv` — idem

**Format CSV (separator `;`)** :
```
day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss
```

Exemples de lignes :
```
0;0;VEV_5400;22;25;;;;;24;25;;;;;23.0;0.0
0;0;VEV_5200;88;24;;;;;90;24;;;;;89.0;0.0
0;0;VELVETFRUIT_EXTRACT;5247;30;5246;45;5245;120;5249;28;5250;50;5251;150;5248.0;0.0
```

J'ai aussi `trades_round_3_day_{0,1,2}.csv` — trades exécutés publics :
```
timestamp;symbol;price;quantity;buyer;seller
```

---

## Ta mission : construire la surface IV et détecter les mispricings persistants

### Tâche 1 — Extraire IV Black-Scholes par ts/day/strike

Pour chaque strike K ∈ {4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500} et chaque timestamp :

1. Calculer `S = mid_price(VE)` au même timestamp
2. Calculer `C_market = mid_price(VEV_K)` au même timestamp
3. Calculer `TTE` restant (début R3 : présumé 7 jours, décroît linéairement sur les 3 jours de data = probablement 7 → 4 sur nos 3 jours)
4. Inverser Black-Scholes pour obtenir l'**implied volatility** σ telle que `C_BS(S, K, TTE, r=0, σ) = C_market`
5. Produire un CSV : `day, timestamp, strike, S, C_market, TTE, IV`

**Attention** : pour les deep ITM/OTM extrêmes (V4000, V6500), l'inversion peut être numériquement instable ou IV indéfinie (prix = intrinsic pur ou ~0). Gère ces cas proprement (flag "pure_intrinsic" ou IV=NaN).

### Tâche 2 — Surface IV empirique

1. Pour chaque `day`, trace **IV moyen par strike** (skew/smile). Est-ce monotone ? U-shape ? Skew gauche ?
2. Pour chaque jour, **fit une parabole** (ou quadratic in log-moneyness) sur IV(K) → c'est la "surface théorique"
3. Calculer pour chaque (ts, K) : `Z = (IV_observed - IV_surface) / std_IV_day`
4. Identifier les strikes avec **|Z| > 2 persistant** (plus de 30% des timestamps sur un jour) → c'est un mispricing systémique

### Tâche 3 — Confirm / infirm les signaux attendus

**Hypothèse Codex initiale** : VEV_5400 IV ~24% alors que surface ~25% → **long VEV_5400**.

Valide ou invalide :
- L'IV VEV_5400 est-elle vraiment systématiquement sous la surface ?
- Sur quel(s) jour(s) ?
- Est-ce un signal tradable (edge en ticks > coût half-spread) ?

**Autres candidats à chercher** :
- Strike avec IV anormalement haute (short candidate)
- Évolution de l'IV dans le temps (term structure intraday — est-ce que la vol cool l'après-midi ?)

### Tâche 4 — Edge chiffré par strike

Pour chaque strike, calculer l'**EV d'un trade long/short** si on suppose que l'IV revient à la surface :
- Half-spread bid/ask observé (coût d'entrée)
- Vega du strike × (IV_surface - IV_observed) = gain théorique si mean reversion
- EV net = gain - coût, en ticks

Classer les 10 strikes par EV décroissant. Recommandation finale : sur lequel poser de la taille, lequel éviter.

---

## Format du livrable

1. **Notebook Python** (ou script) reproductible qui tourne en <2 min sur mes CSVs
2. **CSV** `iv_surface.csv` avec les IV extraites
3. **Graphes PNG** : (a) surface IV par jour, (b) Z-scores par strike dans le temps, (c) EV par strike
4. **Résumé texte** (~300 mots) : verdict par strike avec action concrète (LONG / SHORT / AVOID)

---

## Notes techniques

- Formule Black-Scholes call : `C = S*N(d1) - K*exp(-rT)*N(d2)` avec `d1 = (ln(S/K) + (r+σ²/2)T) / (σ√T)`, `d2 = d1 - σ√T`
- Utilise `scipy.optimize.brentq` pour l'inversion IV (robuste)
- TTE en années : `TTE_years = days_remaining / 250` (année de trading) ou `/365` (calendrier). Je te laisse choisir mais sois cohérent.
- Position limits : HYD=80, VE=200, VEV variable (50-200). Pertinent pour sizing des recommandations.

---

## Quelle question prioritaire ?

Si tu devais ne répondre qu'à **une seule** chose : **quels strikes VEV sont-ils systématiquement mal prices, long ou short, et avec quel edge en ticks ?**
