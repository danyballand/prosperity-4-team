# PROMPT GPT AGENT PRO — IMC Prosperity 4 Round 3 Alpha Discovery

## ⚠️ Mode opératoire attendu

Tu es en **Agent Mode** avec accès à :
- **Browsing web** (utilise-le : Wiki IMC, GitHub, Discord archives, Reddit, Arxiv)
- **Python sandbox** (utilise-le : j'ai des CSVs à analyser, pandas/scipy/statsmodels disponibles)
- **Reasoning long** (utilise-le : on veut des insights non-évidents)
- **Chain-of-thought itératif** (hypothèse → test → revise)

**Ne te contente pas de répondre vite.** Je veux que tu **explores**, **itères**, et **croises les sources**. Prends 10-15 min si besoin.

Si tu as le choix entre une réponse rapide et une session longue avec plusieurs itérations, **choisis toujours la seconde**.

---

## Qui je suis / le contexte

Je suis **Dany**, lead dev d'une équipe de 2 qui participe à **IMC Prosperity 4** (challenge de trading algorithmique organisé par IMC Trading, 24 avril 2026). On a fini **Round 1 rang #366 mondial** (+12,157 seashells), Round 2 similaire. On attaque **Round 3**.

**Language de dev** : Python 3 uniquement. Format IMC : une classe `Trader` avec méthode `run(state) -> (orders, conv, trader_data)`. Simulation 100% déterministe en local, avec variance en live (80% random sampling des quotes dans leur simu).

**Équipe** : on ne peut soumettre que UNE fois final par round, mais plusieurs tests intermédiaires. Le submit final est celui qui compte. Méthodo stricte : jamais de submit sans backtest 3 jours + audit PnL par produit.

---

## Univers R3 (ce que je sais)

**12 produits** dans nos CSVs :

| Produit | Type | Prix obs | Spread | Limit présumé |
|---------|------|----------|--------|---------------|
| `HYDROGEL_PACK` | stable | ~10,000 | 16 | 80 |
| `VELVETFRUIT_EXTRACT` (VE) | **underlying** | 5247-5295 | 5 | 200 |
| `VEV_4000` | call K=4000 | ~1250 (deep ITM) | 2 | 200 |
| `VEV_4500` | call K=4500 | ~750 (deep ITM) | 2 | 200 |
| `VEV_5000` | call K=5000 (ITM) | ~260 | 2 | 100 |
| `VEV_5100` | call K=5100 (ITM) | ~170 | 2 | 100 |
| `VEV_5200` | call K=5200 (near ATM) | ~90 | 2 | 100 |
| `VEV_5300` | call K=5300 (ATM) | ~50 | 2 | 80 |
| `VEV_5400` | call K=5400 (OTM) | ~24 | 2 | 80 |
| `VEV_5500` | call K=5500 (OTM) | ~12 | 2 | 80 |
| `VEV_6000` | call K=6000 (deep OTM) | ~1 | 1 | 50 |
| `VEV_6500` | call K=6500 (deep OTM) | ~0 | 1 | 50 |

**TTE** : **présumé** 7 jours à t=0 de R3, r=0.

**Ces données sont PRÉSUMÉES** — je n'ai PAS accès à la Wiki officielle IMC. **Une de tes premières tâches = aller vérifier / corriger sur le Wiki IMC Prosperity 4.**

---

## Mon baseline actuel

Trader MM passif (pennying, triple_edge, Kalman fair value) = **+23,929 seashells sur 3 jours backtest**, en ne tradant QUE :
- HYDROGEL_PACK (+8,778)
- VELVETFRUIT_EXTRACT (+7,845) avec wall_mid adaptatif
- VEV_4000 (+5,247) — deep ITM, quasi delta 1
- VEV_4500 (+689), VEV_5000 (+661), VEV_5100 (+709)

Les **VEV 5200 → 6500 sont désactivés** (position_limit=0) car mon MM sans pricing options saigne dessus (adverse selection violente). **Je veux les réactiver mais proprement.**

---

## Données que je te fournis (voir fichiers attachés)

Dans le zip `r3_data.zip` :
- `prices_round_3_day_0.csv` (6.5 MB, ~120k rows)
- `prices_round_3_day_1.csv`
- `prices_round_3_day_2.csv`
- `trades_round_3_day_0.csv` (50 KB)
- `trades_round_3_day_1.csv`
- `trades_round_3_day_2.csv`

**Format prices (sep `;`)** :
```
day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss
```

**Format trades (sep `;`)** :
```
timestamp;symbol;price;quantity;buyer;seller
```

Les `buyer`/`seller` sont des IDs pseudonymes (non-null = trader observable, peut être tracké).

---

## Ta mission — en 6 phases

### PHASE 1 — Intelligence externe (~15 min browsing)

Utilise le browser pour :

1. **Wiki IMC Prosperity 4 officielle** — cherche "imc prosperity 4 round 3 wiki" ou "imc-prosperity". **Extrais** :
   - Position limits exactes des 12 produits
   - TTE initial et règle de décompte
   - Règles de settlement (exercise automatique ? cash-settled ?)
   - Règles "Manual trading" de R3 (il y a souvent une manual alloc R3)
   - Bidding / MAF (actif en R3 ?)

2. **GitHub** — cherche des repos publics `imc-prosperity-3 round-3` (Prosperity 3 avait aussi un round options). Il doit y avoir 5-10 repos publics de teams qui ont documenté leurs stratégies. **Extrais** leurs approches options.

3. **Discord archives / Reddit r/algotrading / r/imcprosperity** — cherche les postmortems des équipes top 10 de Prosperity 3 sur leur round options.

4. **Arxiv / Avellaneda-Stoikov** — cherche 2-3 papers clés sur "options market making with adverse selection" ou "IV surface estimation high frequency". Donne-moi les principes directement applicables à R3.

**Livrable phase 1** : un résumé structuré de ce que tu as trouvé officiellement + inspirations stratégiques externes + confirmation/correction de mes présomptions sur les limits/TTE.

### PHASE 2 — Analyse quantitative data (~20 min Python)

Lance le Python sandbox. Charge les CSVs. Fais :

1. **Extraire IV Black-Scholes par ts/strike/jour** (TTE depuis phase 1 si trouvé, sinon 7j)
2. **Surface IV** (skew/smile, évolution intra-day, term structure)
3. **Delta empirique** par strike (regression `dVEV/dVE`)
4. **Mispricings persistants** (Z-score vs surface lissée, |Z| > 2 sur > 30% des obs)
5. **Corrélations** pairwise entre tous les VEVs + HYD + VE
6. **Butterfly violations** : `C(K-Δ) - 2C(K) + C(K+Δ) >= 0` ? Y a-t-il des arbs purs ?
7. **Trader ID profiling** (si buyer/seller IDs présents) : top 5 IDs les plus profitables, patterns
8. **Markout par trade size** : les gros trades ont-ils un markout biased = informed flow
9. **OBI predictive power** : OBI → mid change 100 ts plus tard
10. **Régimes temporels** : volume / vol / adverse selection par tranche de ts

**Livrable phase 2** : DataFrame récap + ~10 graphes PNG + insights numériques chiffrés.

### PHASE 3 — Reasoning approfondi (~10 min thinking)

**Use your deep reasoning.** Avec tes findings phase 1+2, pense longuement à :

1. **Quels sont les 3 plus grosses sources d'alpha possibles en R3 ?** (réactive VEVs disabled + comment, delta hedging, butterfly arb, informed flow, vol risk premium...)
2. **Quelle est la structure de risque idéale** (delta neutral ? vega neutral ? long gamma ?)
3. **Quel est le CONTRE-scénario pire** (si ta stratégie est contre-productive, qu'est-ce qui se passe ?)
4. **Quelles sont les HYPOTHÈSES implicites** de ma baseline qui pourraient casser en live ?
5. **Y a-t-il un "side channel" caché** dans les données (effet surprenant observable) ? Explore methodiquement les hooks non-obvious (timing, trader_data state, ordre des orders, etc.)

**Ne saute pas cette phase.** C'est là que ton avantage vs Codex se joue : la profondeur de raisonnement.

### PHASE 4 — Synthèse stratégique (~5 min)

Produis UN seul document "strategy.md" qui contient :

1. **Executive summary** (3 bullets, 50 mots max)
2. **Changements recommandés** à mon trader, par ordre de priorité, avec EV estimé :
   - Changement 1 : ... (EV +X seashells/jour)
   - Changement 2 : ... (EV +Y)
   - ...
3. **Code Python** prêt à coller (module BS pricing + logique de signal + delta hedge)
4. **Risques identifiés** + mitigations
5. **Plan de validation** : comment tester que ça marche (backtest sur quels jours, quoi surveiller)
6. **Plan B** : si changement 1 échoue en live, fallback ?

### PHASE 5 — Code exécutable

Écris-moi :
1. `bs_pricing.py` — module autonome : `call_price(S,K,T,r,sigma)`, `implied_vol(C,S,K,T,r)`, `delta(S,K,T,r,sigma)`, `vega(...)`, `theta(...)`, testé avec assertions
2. **Patch** `trader_r3.py` — bloc à insérer pour pricing options + réactiver VEV_5200/5300/5400/5500 avec edges basés sur IV surface fit
3. **Fonction de signal** long VEV_5400 si IV < surface + hedge VE automatique

### PHASE 6 — Questions à me poser

Finis par **3 questions ouvertes** que tu me poses, pour valider avant intégration :
- Choses que tu n'as pas pu vérifier seul
- Trade-offs où tu veux mon input (risk vs reward)
- Infos manquantes qui bloquent

---

## Contraintes absolues

- **Déterminisme** : le code soumis doit être 100% déterministe (pas de `random`, pas de `time.time()`). La variance en live vient de la simu IMC, pas du code.
- **trader_data limit** : 49,000 bytes max par sérialisation (JSON). Attention si tu stockes l'IV history.
- **Timeout** : chaque `run()` doit tourner en <900 ms en local (IMC kill les runs trop longs).
- **Pas de `print`** spam en prod (OK pour debug backtest, vire en submit).
- **Backward compat** : je dois pouvoir toggle ton changement avec un flag (e.g. `"enable_bs_pricing": True`) pour A/B test.

---

## Ce que je NE veux PAS

- Des généralités sur le market making ("il faut gérer l'inventaire", "attention à l'adverse selection" — je sais)
- Des suggestions sans chiffrage (chaque recommandation doit avoir EV en seashells ou edge en ticks)
- Du code dépendant de libs externes non-standard (scipy OK, sklearn OK, torch NON)
- De la stratégie overfittée sur 3 jours sans test de robustesse (split train/test ou bootstrap)

---

## Ce que je VEUX

- Une stratégie **quantifiée** avec EV chiffré
- Du code **testé** avec assertions
- Des **raisonnements explicites** (pas juste "fais ça", mais "fais ça parce que X montre Y donc Z")
- Un **plan d'action** séquencé (étape 1, 2, 3 ... avec critères de passage)
- L'identification d'**au moins 1 pattern non-obvious** dans la data (side channel, régime, anomalie)

---

## Go. Utilise toutes tes capacités. Prends ton temps.
