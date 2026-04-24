# Synthèse P2 (delta hedge) + P3 (microstructure)

> **Date** : 2026-04-24 · Après Codex P2 + P3 reçus
> **Statut** : rewrite partiel de la stratégie pair trade — le SHORT 5300 n'est plus viable

## TL;DR — La stratégie du pair trade doit évoluer

Findings P3 nous oblige à **changer l'angle** sur la jambe SHORT VEV_5300 :

| Strike | Buy trades (3j) | Sell trades (3j) | Tilt |
|---|---:|---:|---|
| VEV_5300 | 1 | 119 | **sell-heavy** |
| VEV_5400 | **0** | 225 | **sell-heavy total** |
| VEV_5500 | 0 | 267 | sell-heavy total |
| VEV_6000 | 0 | 284 | sell-heavy total |

**Implication critique** : sur VEV_5300 et VEV_5400, **tous les trades publics sont des sells**.
- ✅ **LONG VEV_5400** fonctionne : on quote le bid, le flux sellers nous remplit facilement.
- ❌ **SHORT VEV_5300** ne fonctionne pas : on quote l'ask, mais personne ne vient buy → zéro fill espéré.

---

## Findings P2 (delta & hedge)

### 1 · Delta empirique vs BS théorique

| Strike | δ empirique | δ BS | Gap | R² (qualité fit) |
|---|---:|---:|---:|---:|
| VEV_4000 | 0.745 | 1.000 | -0.255 | 0.35 (fragile) |
| VEV_4500 | 0.662 | 1.000 | -0.338 | 0.36 |
| VEV_5000 | 0.653 | 0.937 | -0.284 | 0.57 |
| VEV_5100 | 0.577 | 0.823 | -0.246 | 0.59 |
| VEV_5200 | 0.437 | 0.624 | -0.187 | 0.51 |
| VEV_5300 | 0.273 | 0.392 | -0.119 | 0.39 |
| **VEV_5400** | **0.129** | **0.182** | **-0.053** | **0.29 (faible)** |
| VEV_5500 | 0.055 | 0.083 | -0.028 | 0.12 |
| VEV_6000 | 0.0 | 0.006 | -0.006 | N/A |
| VEV_6500 | 0.0 | 0.004 | -0.004 | N/A |

**Pattern frappant** : **tous les δ_empiriques sont ~70% du δ_BS**. Cause probable : sticky quotes des MMs (ils ne reprice pas à chaque tick VE) + regression dilution bias (bruit dans dC qui atténue le β).

### 2 · Lead/lag — tous nuls

Sur tous les strikes actionnables, **lag optimal = 0** (mouvement synchrone VE↔VEV). Aucun signal "VEV leade VE" exploitable. Interprétation : les MMs VEV reprice en temps réel, pas d'informed flow directionnel côté options.

### 3 · Rolling delta stability

| Strike | std(δ rolling) | Verdict |
|---|---:|---|
| VEV_4000 | 0.090 | fragile (swing ±0.18 à 2σ) |
| VEV_4500 | 0.076 | fragile |
| VEV_5000 | 0.060 | modéré |
| **VEV_5300** | **0.040** | **stable** |
| **VEV_5400** | **0.025** | **très stable** |
| VEV_5500 | 0.026 | stable (mais illiquide) |

**Bonne nouvelle** : le delta de VEV_5400 (notre leg LONG) est **le plus stable** de tous. On peut hedger avec confiance.

### 4 · Cross-VEV hedging

Aucune paire avec `corr(dC) > 0.95` → pas de hedge intra-options possible. Le hedge doit se faire via VE.

---

## Findings P3 (microstructure)

### 1 · Danger level

| Produit | Danger | Markout 500ts | Interprétation |
|---|---|---:|---|
| VELVETFRUIT_EXTRACT | **HIGH** | +1.81 | Gros adverse selection, attention MM |
| VEV_5200 | MEDIUM | +0.17 | Marginal |
| VEV_5300 | LOW | +0.24 | Safe |
| **VEV_5400** | **LOW** | **+0.02** | **Très safe pour MM** |
| HYDROGEL_PACK | LOW | -0.32 | **Edge inverse (on gagne à MM)** |
| VEV_5500, 6000, 6500 | LOW | ~0 | Illiquide |

**VE est dangereux** — confirme la nécessité de quote serré avec edge min 3 ticks, pas d'agressivité.

### 2 · Identifiants traders

**Tous les buyer/seller IDs sont vides (100%)** — confirmation : **pas de side channel trader** en R3 (contraire à R1/R2). Pas la peine de tracker les ID.

### 3 · Asymétrie buy/sell

**SHOCK finding — tous les strikes VEV_5300+ sont totalement sell-heavy** :
- VEV_5400 : 0 buyers, 225 sellers
- VEV_5300 : 1 buyer, 119 sellers
- VEV_5500 : 0 buyers, 267 sellers
- VEV_6000 : 0 buyers, 284 sellers
- VEV_6500 : 0 buyers, 284 sellers

**Interprétation** : le marché est **saturé de vendeurs d'options OTM**. Personne n'achète. Ça explique l'IV systémiquement sous la surface — c'est la pression retail qui écrase les prix, pas un bug du MM.

**Implications stratégiques** :
1. **LONG VEV_5400 via skewed MM bid** → on a un flux de sellers constant → on remplit facilement ✅
2. **SHORT VEV_5300 via skewed MM ask** → on n'aura PAS de fills (personne ne buy) ❌
3. **Nouvelle stratégie** : LONG VEV_5400 unilatéral + hedge direct VE, pas de pair trade

### 4 · OBI predictivity

**OBI est contrarien sur VE et HYD** :
- OBI fortement négatif (sellers dominant) → mid MONTE de 0.28 ticks sur 500 ts
- OBI fortement positif (buyers dominant) → mid BAISSE de 0.16 ticks

**Recommandation** : skew **inverse** sur VE → si OBI négatif, on peut acheter à la marge (contrarien). Pas énorme mais confirme qu'un simple OBI skew classique serait contre-productif.

### 5 · Bins temporels

| Type | Bins ts |
|---|---|
| À éviter (risque élevé) | 910k-919k, 280k-289k, 10k-19k, 640k-649k, 230k-239k |
| Préférables (calmes) | 660k-669k, 670k-679k, 0-9.9k, 330k-339k, 960k-969k |

Utilisable pour **élargir le make_edge** pendant les bins dangereux et resserrer pendant les calmes. Gain marginal mais réel.

---

## Nouvelle stratégie : LONG VEV_5400 unilatéral + hedge VE direct

### Principe

Au lieu du pair trade 5300/5400 qui ne peut pas se faire (SHORT 5300 impossible en skewed MM), on part sur **LONG VEV_5400 simple** :

1. **Quote bid VEV_5400** en pennying (bid_market + 1)
2. Le flux sellers infini nous remplit jusqu'à +40 ou +60 contracts
3. **Hedge via short VE** : net delta = 40 × 0.129 = +5.16 → short 5 VE
4. **Hold jusqu'à expiry** ou convergence IV (improbable)

### PnL scenarios (40 LONG 5400 + 5 SHORT VE)

**Cash initial** :
- LONG 40 × VEV_5400 @ 15 = -600 SS
- SHORT 5 × VE @ 5250 = +26,250 SS
- Net cash = +25,650 SS (mais on a accumulé inventaire)

**À l'expiry (S_exp = prix VE)** :

| S_exp | VEV_5400 payout (40 × max(S-5400,0)) | VE liquidation (-5 × S) | PnL total |
|---|---:|---:|---:|
| 5150 | 0 | -25,750 | **-100** |
| 5200 | 0 | -26,000 | **-350** |
| 5250 | 0 | -26,250 | **-600** |
| 5300 | 0 | -26,500 | **-850** |
| 5350 | 0 | -26,750 | **-1,100** |
| 5400 | 0 | -27,000 | **-1,350** |
| 5450 | 2,000 | -27,250 | **+400** |
| 5500 | 4,000 | -27,500 | **+2,150** |
| 5600 | 8,000 | -28,000 | **+5,650** |

**Problème** : le payoff est **mauvais** si VE reste dans le range 5200-5400 (le plus probable !). On paie le premium et on perd sur le hedge.

### Pourquoi ça ne marche PAS comme ça

Le raisonnement initial supposait qu'on **capture l'edge IV de +1.43 ticks à l'entrée** (= on achète sous la fair value). Mais à l'expiry, on ne capture que l'intrinsic. Le +1.43 edge n'est matérialisé **que si on sort avant expiry** à un prix proche de la fair surface value.

**Condition de profit** : il faut que le marché reprice VEV_5400 **AVANT l'expiry**. Or P1 montre que l'IV diverge (ne converge pas) sur 3 jours → **risque majeur que ça ne se reprice jamais avant expiry**.

---

## Alternative 1 — "Pair calendar" avec un VEV adjacent qui se laisse shorter

Chercher un strike qui est **achetable** (pas sell-heavy) pour faire la jambe SHORT du pair :

Candidats :
- VEV_4000, VEV_4500 : balanced buy/sell. Mais deltas énormes (0.66-0.75) → hedge VE lourd
- VEV_5200 : sell-heavy aussi (1 buy / 17 sells). Pas utilisable.

**Verdict** : aucun strike ne permet le SHORT skewed MM sur l'axe ATM-OTM. Pair trade classique impossible.

---

## Alternative 2 — "Structural short" via quote 5400 ask large

Au lieu de pennying bid, **aggressive MM skewed** :
- Quote bid VEV_5400 serré (build long position)
- **Quote ask VEV_5400 au prix surface + 1 tick** = 18-20 SS (au-dessus du market ask 17)
- Si flux d'acheteur apparait → on récupère la prime + réalise +1.43 edge

Mais d'après P3, **0 acheteurs sur VEV_5400** → quote ask ne se rempliera jamais. Donc inutile.

---

## Alternative 3 — "Buy and hold" sur le directional delta risk

Constatation : le marché vend massivement les OTM → il **sous-évalue la probabilité d'ITM**. Si on pense comme un assureur :
- On **achète la vol cheap** (long 5400)
- On **hedge le delta** (short 5 VE par 40 contracts)
- On **subit le theta** (~-0.05/ts × 100,000 ts/jour = -5,000 per 40 contracts)

⚠️ Problème : theta. Sur 3 jours de hold, 40 contracts perdent ~15,000 en theta, soit -375 SS. Plus grand que notre edge +1.43 × 40 = 57 SS. **Net négatif**.

---

## Alternative 4 — Exploiter le flux sellers VEV_5400 avec clearing rapide

Nouvelle stratégie : **scalping du flux sellers** :
1. **Quote bid** VEV_5400 légèrement inside (bid_market + 1)
2. Fill → on est long
3. **Immédiatement** : quote ask VEV_5400 à prix mid + 1 (ou mid + 0.5 si prix impair pas possible)
4. Mid bouge → on flatten en quelques ts
5. Capture = 1 tick de spread en net

**EV** : 1 tick × 40 trades × 3 jours = **+120 SS**. Modeste mais positif et low-risk.

**Défi** : si le mid ne bouge pas → on accumule long sans pouvoir flatten. Cap inventory à +20 max pour éviter.

---

## Alternative 5 (préférée) — Skip options trading, optimiser baseline

**Constatation pragmatique** : l'edge IV +1.43 ticks est théorique. En pratique :
- On ne capture PAS l'edge si on hold to expiry (payoff intrinsic)
- On ne peut PAS trader la convergence IV (elle ne converge pas en 3 jours)
- Le theta mange l'edge sur un hold court

**Décision proposée** : 
1. **Garder baseline v2** (+23,929 SS en backtest)
2. **Optimiser HYD** (tester make_edge 80, 90, 97, 105, 110) → gain marginal potentiel +2k
3. **Optimiser VE** (tester use_microprice variants, make_edge 2-5) → gain marginal +1k
4. **Submit safe baseline** + exploration R3 via submits successifs

**EV upside réaliste** : +23,929 → +28,000 SS en optimisation paramétrique. Pas d'alpha options extrait mais pas de risque non plus.

---

## Décision pour Dany

Trois chemins possibles :

### A · Safe play (recommandé)
- Baseline v2 + tuning paramétrique HYD/VE
- Submit à ~+28k SS backtest
- Risque : minimal. Upside : +4k vs baseline.

### B · Scalping VEV_5400 (modéré)
- Baseline v2 + scalping bid→ask sur VEV_5400 (Alternative 4)
- Cap inventory +20
- Submit à ~+24k + 120 SS scalping
- Risque : faible. Upside : +120 SS si ça fonctionne, pire case -500 SS si pris long sans exit.

### C · Full alpha tentative (risqué)
- LONG VEV_5400 + hedge VE (Alternative 3)
- Submit à ~+22k backtest (baseline -2k de theta drag)
- Risque : élevé. Upside : très dépendant du S_exp final.
- **Pas recommandé vu les findings P3**.

---

## Questions pour Codex (follow-up P1/P2/P3)

Avec tout ce qu'on a appris, les questions prioritaires restantes :

1. **Rolling surface IV** (du P1_FOLLOWUP) : est-ce que l'edge +1.43 ticks se manifeste en **intraday** avec fenêtre 500 ts ? Si oui → scalping possible même sans convergence quotidienne.

2. **Volume d'exécution réaliste** : vu que VEV_5400 est 0 buy / 225 sell, quelle taille on peut réellement **acheter au bid en 1 jour** sans bouger le prix ? Si on peut absorber 100 contracts/jour, l'edge devient intéressant.

3. **Theta empirique vs théorique** : sur 3 jours, combien VEV_5400 a réellement perdu en valeur (hors S-move) ? Si theta réalisé < theta BS → l'edge est plus grand que le theta drag.

4. **Pair calendar alternative** : puisqu'on ne peut pas SHORT 5300 au skewed MM, est-ce qu'on peut **SHORT VE directement** comme leg inverse du pair ? Le ratio nécessaire serait gros mais VE est liquide.

---

## Prochaine étape

Je propose de :
1. **Lancer follow-up P1** (rolling surface + theta empirique) pour confirmer/infirmer le scalping
2. **En parallèle, tuner HYD et VE** pour sécuriser +4k vs baseline
3. **Décider** entre A/B/C en fonction du follow-up

À toi de valider ou pivoter.
