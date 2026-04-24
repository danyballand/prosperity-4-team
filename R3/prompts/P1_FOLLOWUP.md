# PROMPT CODEX P1 — Follow-up (5 questions)

## Contexte

Merci pour l'analyse P1 IV Surface. Tu as livré :
- `iv_surface.csv`, `iv_surface_by_day_summary.csv`, `iv_surface_overall_summary.csv`
- `summary.txt` avec verdict clair (5400 LONG +1.43, 5300 SHORT +1.32)
- 3 graphes PNG

**Verdict principal validé** : pair trade LONG VEV_5400 / SHORT VEV_5300, signal stable et croissant sur les 3 jours.

Avant que je code l'intégration, j'ai **5 questions follow-up** pour affiner la mise en œuvre.

---

## Question 1 — Stabilité inter-day du fit quadratique

Tu fites une parabole en log-moneyness par jour avec coefs `(a, b, c)`. Les `fit_diagnostics.csv` donnent :

| day | coef_quad | coef_linear | coef_intercept | residual_std |
|---|---:|---:|---:|---:|
| 0 | 6.44 | -0.037 | 0.208 | 0.0127 |
| 1 | 7.30 | -0.021 | 0.212 | 0.0163 |
| 2 | 8.46 | +0.004 | 0.216 | 0.0203 |

**Le coef quadratique passe de 6.4 à 8.5 en 3 jours** — la surface se **"raidit"** (smile plus creusé). Le coef linéaire change de signe (-0.037 → +0.004) : pente inverse.

### Questions précises :
1. Cette dérive est-elle due au **time decay** (quand TTE baisse, le smile se raidit mécaniquement) ou à un **changement de régime** des traders informés ?
2. Si je fite la surface sur une **rolling window de 500 ts** (au lieu de full day), est-ce que l'edge +1.43 sur VEV_5400 est stable ou disparaît ?
3. Peut-on fiter une **surface 2D (strike × time)** unifiée sur les 3 jours avec un modèle `a(T) × ln(K/S)² + b(T) × ln(K/S) + c(T)` où `a, b, c` sont fonctions linéaires de T ? Ça donnerait une surface prévisible pour les jours live.

**Livrable** : CSV supplémentaire `rolling_surface_iv.csv` avec résidu calculé sur rolling 500ts, et vérifier si edge 5400/5300 tient.

---

## Question 2 — Fréquence des fills

Tu as compté :
- VEV_5400 : **225 trades publics sur 3 jours** (75/jour)
- VEV_5300 : **121 trades publics sur 3 jours** (40/jour)

Ma stratégie veut build +40 sur 5400 et -40 sur 5300 en skewed MM (quote one-sided).

### Questions précises :
1. Quelle est la **distribution des tailles de trades** sur chaque strike ? (histogramme). Si les trades moyens sont 1-2 contracts, j'ai besoin de 20-40 fills pour build ma position.
2. Quel est le **temps moyen entre deux trades** sur chaque strike ? Si c'est 1000 ts, je mets 40,000 ts (≈4,000 ms) pour build — trop long.
3. Si je compare le **flux public** (vu dans trades.csv) au **flux observable dans les ordres** (vu dans prices.csv : volume ajusté à chaque tick), y a-t-il un gap ? Autrement dit, est-ce que des trades ont lieu qu'on ne voit pas dans `trades.csv` ?
4. **Quelle fraction du flux public** a lieu **at bid** vs **at ask** vs **at mid** ? Si 80% du flux 5400 est at-ask (hit by aggressive buyers), mon skewed MM bid capturera peu. Inversement pour 5300.

**Livrable** : `trade_flow_analysis.csv` par strike avec ces métriques + recommandation taille max réaliste atteignable par jour.

---

## Question 3 — Corrélation résidu ↔ move VE

### Hypothèse à tester :
Si VE monte, les VEV ATM gagnent mécaniquement en IV (gamma). Si le résidu 5400 cheap se creuse quand VE descend, on a un **skew dynamique** qu'il faut tradeuer intelligemment (vendre 5400 cheap quand VE monte, acheter quand VE descend).

### Questions précises :
1. Regresser `residu_5400(t)` sur `(S(t) - S̄)` : existe-t-il un β significatif ? Même question pour 5300.
2. Regresser `residu_5400(t)` sur `dS(t)` (move court terme) : est-ce que le résidu est généré par des **flux qui répondent aux moves** ?
3. Tester si le résidu 5400 est **auto-corrélé** (AR(1) coefficient) : s'il l'est, on a une information de timing pour l'entrée (attendre que le résidu soit très négatif avant d'acheter).
4. Le résidu 5400 a-t-il un **régime "calme" vs "agité"** selon l'heure de la journée (par tranche de 100k ts) ?

**Livrable** : régressions + scatter `residu vs dS` + autocorr plot, et recommandation : trader le pair spread constant, ou timing intelligent ?

---

## Question 4 — Test du pair spread 5300 - 5400 en prix

### Hypothèse :
Au lieu de trader chaque leg séparément, tester le **spread price 5300 - 5400** directement. Il est théoriquement borné et mean-reverting.

### Questions précises :
1. Calculer `spread_t = price_5300(t) - price_5400(t)` sur les 3 jours
2. Statistiques : mean, std, min, max, autocorr, half-life (Ornstein-Uhlenbeck)
3. Tester un signal simple : **LONG spread (= LONG 5300 + SHORT 5400) si spread < μ - σ**. Non attends — c'est l'inverse de notre pair trade original. On veut **SHORT spread (= SHORT 5300 + LONG 5400) si spread > μ + σ** (spread anormalement large = signal).
4. Comparer l'EV de ce **signal en timing intelligent** vs **position statique** (garder la paire tout le temps).

**Livrable** : série temporelle spread + graph mean-reversion + backtest du signal avec EV chiffrée.

---

## Question 5 — Test sensibilité TTE

Tu as assumé TTE = 7 jours à t=0, décroît linéairement. Mais c'est présumé (on n'a pas le Wiki officiel).

### Questions précises :
1. Refaire l'analyse **IV surface avec TTE=5j** (scénario court) et **TTE=10j** (scénario long). L'edge VEV_5400 change-t-il ? Reste-t-il positif ?
2. Si TTE est en réalité fonction **heure-par-heure** (e.g. 1 jour de data = 1 jour de calendar), modifier en conséquence.
3. Tester l'hypothèse que le TTE est **en années de trading (250)** vs **années calendrier (365)** : quelle IV est la plus "réaliste" (compatible avec nos intuitions de marché, IV calls ATM typiques 15-25%) ?

**Livrable** : table de sensibilité :
```
TTE_assumption, edge_5400_long, edge_5300_short, verdict
7j x 250       +1.43          +1.32            BASELINE
5j x 250       ???            ???              ???
10j x 250      ???            ???              ???
7j x 365       ???            ???              ???
```

Et recommandation : quelle valeur TTE est la plus plausible ?

---

## Format livrable attendu

- 4 CSVs supplémentaires (ou ajoutés aux existants)
- 4-5 graphes PNG (rolling surface, trade flow dist, residu vs dS, spread timeseries, TTE sensitivity)
- Un paragraphe de conclusion pour chaque question, avec verdict clair : **"GO / CAUTION / NO-GO"** pour le pair trade dans les conditions testées.

---

## Important

**Tu n'as pas besoin de refaire l'analyse complète.** Réutilise `iv_surface.csv` que tu as déjà produit et ajoute uniquement les nouveaux angles.

Si tu identifies un **insight inattendu** en cours de route (side channel, anomalie non évoquée), **flag-le en priorité**.
