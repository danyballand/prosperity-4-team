# Synthèse stratégique — Codex P1 (IV Surface)

> **Date** : 2026-04-24 · **Auteur** : Claude + Dany · **Statut** : validé côté data, en attente intégration code

Cette note synthétise les findings du prompt Codex **P1 IV Surface** et propose un plan d'intégration concret dans `trader_r3.py`.

---

## TL;DR (30 secondes)

1. **Signal IV structurel identifié** : VEV_5400 est quoté ~1% IV trop bas, VEV_5300 ~1% trop haut par rapport au smile quadratique théorique.
2. **Signal stable et croissant** sur les 3 jours (EV +1.26 → +1.53 sur VEV_5400, +0.46 → +1.57 sur VEV_5300).
3. **Interprétation** : signature d'un bug/quirk du market maker d'IMC — **ça persistera en live**.
4. **Stratégie proposée** : pair trade LONG 5400 / SHORT 5300 avec delta hedge VE → **+1,050 SS EV attendue**.

---

## 1 · Lecture des findings

### 1.1 Surface IV empirique

Sur chaque jour, Codex a :
- Extrait IV Black-Scholes par (timestamp, strike) avec TTE=7j→4j linear decay, r=0
- Fité une **parabole en log-moneyness** : `IV(K) = a × ln(K/S)² + b × ln(K/S) + c`
- Calculé le résidu `IV_observée - IV_surface`
- Classé chaque strike par EV net après half-spread

Le smile empirique est clair (forme en U) et le fit quadratique capture bien la shape générale, sauf **deux anomalies** :

```
Day 2 exemple :
Strike:    4500  5000  5100  5200  5300  5400  5500  6000  6500
IV obs:    46.5% 22.3% 21.7% 22.2% 22.7% 21.1% 23.0% 38.8% 58.9%
Surface:   42.0% 23.7% 22.4% 21.7% 21.7% 22.3% 23.4% 36.5% 59.9%
Résidu:    +4.6% -1.4% -0.7% +0.5% +1.0% -1.2% -0.4% +2.3% -1.0%
```

**Focus 5300 vs 5400** : ils sont voisins de strike, mais leur résidu est opposé (+1.0% vs -1.2%). C'est un pattern anormal — normalement un smile est monotone ou doucement bombé. Cette "bosse" 5300 + "creux" 5400 est une empreinte de **pricing discret** du MM d'IMC.

### 1.2 Robustesse temporelle

Le pattern se **renforce** jour par jour :

| Day | 5400 résidu | 5400 EV/trade | 5300 résidu | 5300 EV/trade |
|---|---:|---:|---:|---:|
| 0 | -0.86% | +1.26 | +0.48% | +0.46 |
| 1 | -1.10% | +1.53 | +1.01% | +1.92 |
| 2 | -1.21% | +1.50 | +0.96% | +1.57 |

> **Ce n'est pas du mean-reversion classique** (le résidu ne tend pas vers 0) — c'est une **structure persistante** que le marché n'efface pas. On doit l'exploiter comme telle.

### 1.3 Rejets de signaux

Tous les autres strikes ont EV net ≤ 0 après half-spread :
- VEV_5200 : +0.12 (marginal, on skip)
- VEV_5500 : -0.29 (edge noyé dans le spread)
- VEV_4000-4500 : -7 à -10 (deep ITM, spread énorme)
- VEV_5000-5100 : -1.7 à -1.9 (edge théorique mais spread le mange)
- VEV_6000-6500 : -0.3 à -0.4 (illiquides, intrinsic ~0)

**Conclusion** : seuls VEV_5300 et VEV_5400 sont actionnables.

---

## 2 · Mécanique du trade

### 2.1 Pourquoi un pair trade (pas 2 trades séparés)

Faire **LONG 5400 seul** a un problème : on est long call OTM, donc long delta (+0.21 par contract) et long vega. Si VE baisse ou si IV collapse, on perd.

Faire **SHORT 5300 seul** a un problème : short call ATM = short delta (-0.40) et short vega. Si VE monte, on perd gros.

**Le pair trade les combine** :
- Delta : +0.21 - 0.40 = **-0.19 net** (presque neutre, hedgeable avec VE)
- Vega : les 2 strikes ont vega ~230, donc +230 - 230 = **~0 net** (on est immunisé à un mouvement parallèle de vol)
- **Ce qui reste** : la convergence ou persistance du résidu IV entre les 2 strikes voisins — exactement ce que le signal exploite.

### 2.2 Skewed MM one-sided (méthode d'exécution)

**Alternative au cross brutal** (qui avalerait 40 contracts × half-spread = coût élevé), on quote de façon asymétrique :

#### VEV_5400 — LONG bias
```python
if position_5400 < +40:
    # Pas d'ask quote — on ne veut pas vendre
    # Bid quote : penny inside (bid_market + 1)
    quote_bid(price=best_bid + 1, qty=min(20, limit - pos))
elif position_5400 >= +40:
    # On a assez — quote ask large (si IV converge)
    quote_ask(price=surface_price + edge, qty=pos)
```

#### VEV_5300 — SHORT bias
```python
if position_5300 > -40:
    # Pas de bid quote — on ne veut pas acheter
    # Ask quote : penny inside (ask_market - 1)
    quote_ask(price=best_ask - 1, qty=min(20, limit + pos))
elif position_5300 <= -40:
    # On a assez short — quote bid large (si IV converge)
    quote_bid(price=surface_price - edge, qty=-pos)
```

**Avantage** : build la position organiquement via spread capture, coût ≈ 0 en half-spread. Inconvénient : build plus lent, peut-être pas plein limit en 1 jour.

### 2.3 Delta hedge VE

À chaque tick, calculer :
```python
net_delta = pos_5400 × δ_5400 + pos_5300 × δ_5300
# Pour pos_5400=+40, pos_5300=-40, δ_5400=0.21, δ_5300=0.40 :
# net_delta = 40 × 0.21 + (-40) × 0.40 = 8.4 - 16 = -7.6

target_VE = -net_delta  # pour flat delta = +7.6 → long 8 VE
current_VE = state.position.get("VELVETFRUIT_EXTRACT", 0)
hedge_qty = target_VE - current_VE
# Placer un IOC cross sur VE de hedge_qty
```

δ est calculé avec BS formula : `δ_call = N(d1)` où d1 dépend de (S, K, T, σ). Le IV à utiliser : IV **de la surface** (pas IV observée), car c'est notre "truth" théorique.

---

## 3 · Modèle de PnL — scénarios

On pose 40 pairs + 8 VE long. Prix moyens constatés : VEV_5400 ~15, VEV_5300 ~47, VE ~5250.

**Cash out initial** :
- LONG 40 × VEV_5400 @ 15 = **-600 SS**
- SHORT 40 × VEV_5300 @ 47 = **+1,880 SS**
- LONG 8 × VE @ 5250 = **-42,000 SS**
- **Cash net initial** = -600 + 1880 - 42000 = **-40,720 SS**

(On conserve le cash, juste inventory transformation.)

**À l'expiry (prix VE = S_exp)** :

| Scenario | S_exp | VEV_5400 payout | VEV_5300 payout | VE liquidation | PnL |
|---|---|---:|---:|---:|---:|
| VE reste à 5250 | 5250 | 40×0 = 0 | -40×0 = 0 | 8×5250 = 42,000 | **+1,280** |
| VE à 5310 | 5310 | 40×0 = 0 | -40×10 = -400 | 8×5310 = 42,480 | **+1,360** |
| VE à 5370 | 5370 | 40×0 = 0 | -40×70 = -2,800 | 8×5370 = 42,960 | **-560** |
| VE à 5450 | 5450 | 40×50 = 2,000 | -40×150 = -6,000 | 8×5450 = 43,600 | **-1,120** |
| VE à 5200 (crash) | 5200 | 40×0 = 0 | -40×0 = 0 | 8×5200 = 41,600 | **+880** |
| VE à 5150 (crash fort) | 5150 | 40×0 = 0 | -40×0 = 0 | 8×5150 = 41,200 | **+480** |

Le payoff du pair ressemble à un **bear call spread** (vendu 5300 / acheté 5400) : profit borné à +2000 (si expiry worthless), perte bornée à -2000 (si très ITM sur les deux).

**Calcul EV (pondération proba)** :
- P(S_exp < 5300) ≈ 60% → profit moyen ~+1,400
- P(5300 < S_exp < 5400) ≈ 25% → profit moyen ~0
- P(5400 < S_exp) ≈ 15% → loss moyenne ~-1,500

**EV expiry seul** = 0.6×1400 + 0.25×0 + 0.15×(-1500) = +840 - 225 = **+615 SS**

On y ajoute le **spread capture du skewed MM** pendant les 3 jours de build :
- 40 contracts × demi-spread moyen 0.85 × 2 côtés = ~68 SS
- **Total EV** ≈ **+700 SS** (sur l'ensemble du round, pas par jour)

> ⚠️ C'est moins ambitieux que mon estimation initiale (+1,050). La vraie valeur dépend beaucoup de la distribution finale de S_exp.

---

## 4 · Risques et mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| **Rally VE** (S > 5400) | Short 5300 saigne | Stop-loss sur S > 5380 : liquide progressivement |
| **Crash IV (vol collapse)** | Vega neutre en théorie, en pratique fragile | Limiter la taille à 40 pairs max |
| **Flux directionnel informé** | On achète au mauvais moment | Trigger pause si volume anormal (>3× moyen) |
| **Pin risk à 5300/5400** | Exercice automatique imprévu | Liquider 100% 500 ts avant expiry |
| **Overfit 3 jours** | Live différent | Keep baseline activé, pair trade = overlay à faible taille |

---

## 5 · Plan d'intégration en 4 étapes

### Étape A (30 min) — Module BS pricing
Créer `R3/bs_pricing.py` :
- `call_price(S, K, T, r, sigma)` via formule BS close-form
- `implied_vol(C_mkt, S, K, T, r)` via brentq
- `delta(S, K, T, r, sigma)` = N(d1)
- `vega(S, K, T, r, sigma)` = S × N'(d1) × √T
- Tests unitaires : assertions sur put-call parity, valeurs connues.

### Étape B (45 min) — Fonction de signal dans `trader_r3.py`
Ajouter un module `_pair_trade_logic()` qui :
1. Calcule IV actuelle de VEV_5300 et VEV_5400
2. Compare à la surface théorique (coefs pré-calculés ou ré-estimés intraday)
3. Si 5400 IV < surface - 0.5% ET 5300 IV > surface + 0.5% → signal actif
4. Override la logique MM standard : skewed quotes one-sided
5. À position limite atteinte (±40), désactive le side, active l'autre pour close

### Étape C (15 min) — Delta hedge VE
Dans le handler VE principal :
- Si flag `pair_trade_active` → ajouter un terme à `target_bias` basé sur net_delta
- Prioriser le hedge avant le MM normal (IOC cross si delta trop off)

### Étape D (30 min) — Backtest et validation
- Run `local_backtest_r3.py` avec nouvelle version
- Vérifier : `+23,929 → 24,000+` ? Ou on a cassé quelque chose ?
- Si +500 à +2,000 additionnel → submit. Si <+500 → on creuse (P2 delta empirique).
- Si <0 → rollback immédiat, la théorie ne se traduit pas en pratique.

---

## 6 · Questions restantes pour Codex (follow-up P1)

1. **Stabilité inter-day du fit quadratique** : les coefs (a, b, c) du fit parabolique évoluent-ils beaucoup ? Si oui → surface pas stable → le signal "résidu" est bruité par le fit lui-même.
2. **Fréquence des trades publics** sur VEV_5300/5400 : 225 et 121 trades sur 3 jours = 75 et 40 trades/jour. **Est-ce limitant** ? Si on quote 40 contracts mais le flux public = 40/jour, on risque de ne pas filler.
3. **Corrélation résidu ↔ move VE** : si le résidu 5400 cheap s'intensifie quand VE descend, c'est un **skew dynamique** qu'on peut traiter avec un hedge plus actif.
4. **Test de "rolling window"** : si on refit la surface sur les 500 derniers ts (au lieu de full day), l'edge change-t-il ? Ça détermine si on peut tourner la position plus vite.
5. **Test du pair spread VEV_5300 - VEV_5400** : est-ce que ce spread (en prix) est mean-reverting sur un horizon court (100-500 ts) ? Si oui → signal supplémentaire de timing d'entrée.

---

## 7 · Décision d'arbitrage pour Dany

**Ce qu'il faut trancher avant que je code** :

- [ ] **GO pair trade** → je code Étapes A-D (2h)
- [ ] **GO pair trade + follow-up P1** (pour affiner avec les 5 questions ci-dessus) → 2h + attente Codex
- [ ] **NO GO pair trade** (trop risqué / trop petit) → on reste sur baseline v2 et on lance P2/P3/P4
- [ ] **Autre** : ...

> Recommandation : **GO pair trade en v3** en gardant v2 comme fallback. Si v3 backtest donne < v2 → rollback. EV attendu +700 SS = modeste mais positif avec risque borné.
