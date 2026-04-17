# Prompt recherche d'alpha — IMC Prosperity 4

Tu es un **chercheur quantitatif senior** spécialisé en microstructure de marché, statistiques inférentielles, et finance mathématique. Je participe à IMC Prosperity 4 (simulation HFT éducative). Mon objectif : trouver des **stratégies d'alpha non conventionnelles** qui pourraient battre mes algos actuels.

Je ne cherche PAS des conseils génériques type "fais du market making". Je cherche :
- **Combinaisons mathématiques non triviales** de signaux
- **Modèles statistiques** non encore testés
- **Propriétés cachées du LOB** (Limit Order Book) exploitables
- **Arbitrages conceptuels** entre produits ou régimes
- **Frameworks académiques** applicables (papers, livres)

---

## 1. Setup du jeu

### Environnement
- **2-10 produits** par round (crescendo de R1 à R5)
- **100,000 ticks par jour** (step = 100 ms, soit 1000 snapshots)
- **Position limits** typiquement 50-350 par produit
- **Chaque tick** tu reçois :
  - `OrderDepth` : 3 niveaux bid + 3 niveaux ask (prix + volume)
  - `market_trades` : trades publics qui ont eu lieu pendant le tick (sans buyer/seller en 2026)
  - `own_trades` : tes propres fills du tick précédent
  - `position` : tes positions actuelles
  - Parfois `observations` : variables exogènes (sunlight, sugar_price, etc.)
- Tu retournes un `Dict[product, List[Order]]` où `Order(price, qty signé)`

### Contraintes
- **Latence** : ordres postés à T sont fillés au mieux à T+100ms (tick suivant)
- **Timeout** : 900ms par `Trader.run`
- **TraderData** : 49k chars de state persistable
- **Pas de call externe** : Python stdlib + `json` + `math` seulement

### Fonctionnement des fills (validé par audit)
1. **Crossing** : ton ordre qui croise le book actuel est fillé instantanément (price priority)
2. **Passive** : ton ordre qui ne croise pas est mis au book, peut être fillé au tick T+1 si :
   - Un market order arrive à ton prix (priorité temps derrière book pré-existant)
   - Un sweep traverse ton prix (priorité totale si tu es inside spread)
3. Le flow public visible (`market_trades`) n'est qu'une **fraction (~5%)** du vrai flow — le reste est invisible

---

## 2. Produits Round 1 (pour benchmark)

### OSMIUM (stable, mean-reverting autour FV=10000)
- Spread typique : 10-20 ticks
- Volatilité faible
- Beaucoup de flow MAKE passif
- **Ma stratégie actuelle** : Kalman FV + triple edge + pennying + inventory clearing
- **PnL live R1** : +4,716 XIREC

### PEPPER (trending +~1000/jour)
- Drift linéaire connu
- Volatilité moyenne
- Flow plus TAKE-heavy
- **Ma stratégie actuelle** : bootstrap long +40 + decay linéaire + trend guard
- **PnL live R1** : +7,443 XIREC

**Total R1 : +12,159 XIREC.** Top ~+15k. Gap = 2,800 XIREC à combler.

---

## 3. Ce que j'ai déjà testé et qui ne marche pas

| Stratégie | Résultat | Raison probable |
|---|---|---|
| Stoikov-Avellaneda (2008) classique | +84 (sur 27k baseline) | Drift term cumulé explose ; spreads trop tight |
| Stoikov avec drift per-tick corrigé | -15,638 | Pas de pennying aggressif |
| Pure buy-and-hold Pep | -4,367 | Manque le spread capture |
| Signal-stack taker (OBI+mom+trend) | **-194k** | Over-trading → friction pure |
| OBI skew sur quotes Osm | -113 | Déjà implicitement dans le Kalman |
| Bayesian arrival prob (Cartea) | 0 | Saturé |
| Linear regression FV on features | +0 à -14k | Data trop noisy ou mal specified |
| Adaptive fixed FV Osm | +157 | Noise, Kalman déjà bon |

**Observation clé** : tout ce qui est "empilement naïf de signaux" échoue. Les signaux individuels (OBI, microprice, trade imbalance) sont déjà capturés par mon Kalman/bootstrap. Il faut **de la non-trivialité**.

---

## 4. Ce que je cherche (taxonomie des pistes)

### A. Microstructure théorique
- **Hawkes processes** : trades comme processus auto-excitant, prédire bursts d'activité
- **Kyle's lambda** (1985) : impact price = f(net order flow), informed vs noise traders
- **Glosten-Milgrom** : spread optimal sous adverse selection, update bayésien du FV après chaque trade
- **Easley-O'Hara PIN** : probability of informed trading, détection de régimes
- **Cartea-Jaimungal-Penalva** : optimal execution avec impact + signal, HJB
- **Obizhaeva-Wang** : optimal liquidation avec LOB resilience
- **Rosenbaum-Lehalle** : queue priority dynamics, fill probability modeling

### B. Statistique avancée
- **Cointegration** (Engle-Granger, Johansen) : pairs/baskets avec stationarity du spread
- **VECM** : erreur-correction vectoriel entre produits liés
- **Ornstein-Uhlenbeck** : mean-reverting avec speed of reversion estimé
- **GARCH / stochastic vol** : vol clustering détectable → ajuster size
- **Regime switching (HMM)** : détection Markov-switching entre modes (trend vs range)
- **Change point detection** : CUSUM, Bayesian online CPD pour breakpoints structurels
- **Wavelet decomposition** : séparer haute/basse fréquence du signal
- **Entropy / mutual information** : détecter dépendances non-linéaires entre features

### C. Machine learning léger (stdlib only)
- **Online linear regression** avec RLS (recursive least squares)
- **Kalman filter multi-variate** : joint estimation FV + drift + vol
- **Exponentially weighted stats** : moyennes/covariances avec décroissance
- **Kernel methods manuels** : RBF / triangular pour smoothing
- **Bayesian online learning** : distribution posterior sur params

### D. Théorie de l'information
- **Kelly criterion** : size optimal = edge / variance, éviter over-leverage
- **Log-optimal betting** sous contraintes (Cover)
- **Information ratio rolling** pour switch between strategies

### E. Market design / arbitrage
- **Lead-lag inter-produits** : si produit A lead B de k ticks, exploiter
- **Basket decomposition** : fair value synthétique via NNLS sur combinaison linéaire
- **Statistical arbitrage** sur résidus d'un facteur model (PCA)
- **Volatility spillover** : vol d'un produit prédit vol d'un autre

### F. LOB dynamics spécifiques
- **Queue position inference** : où suis-je dans la queue ? (via volume/time)
- **Order flow imbalance (OFI)** vs OBI (Cont, Kukanov, Stoikov 2014) — ∂volume bid/ask
- **Spread crossing frequency** : fréquence où trade happens inside spread
- **Book pressure** : gradient de depth sur les N niveaux
- **Toxic flow detection** : qui cross après nous nous coûte-t-il ?
- **Price impact decomposition** : permanent vs temporary (Almgren 2001)

### G. Idées non conventionnelles
- **Game theory sur les bots adverses** : si un bot systématiquement penny, exploiter son pattern
- **Co-intégration avec dépendance non-linéaire** (copula)
- **Transfer entropy** entre produits : direction causale info
- **Fractal dimension** (Hurst exponent) : persistence vs mean-reversion
- **Extreme value theory** : modéliser les queues de distribution pour risk management

---

## 5. Critères pour qu'une proposition soit valable

Une stratégie que tu me proposes doit avoir :

1. **Formulation mathématique précise** (équations, pas seulement "on utilise X")
2. **Intuition économique claire** (pourquoi ça devrait marcher, quel edge est capturé)
3. **Applicabilité concrète** à mon setup (données disponibles, stdlib only, <100ms compute)
4. **Stratégie d'estimation des params** depuis les CSV training
5. **Diagnostic** : comment vérifier empiriquement que le modèle capture bien la dynamique
6. **Risque** : dans quel scénario ça explose, comment limiter le downside
7. **Originalité** vs ce qui a déjà été testé (voir liste §3)

---

## 6. Format de réponse attendu

Pour chaque idée, structure :

```markdown
## Idée N : [NOM]

### Intuition (2 phrases)
Pourquoi cette idée pourrait capturer de l'alpha que mon v31 rate.

### Formulation mathématique
[Équations, notations, hypothèses]

### Implémentation (pseudo-code Python)
[30-50 lignes max, compatible stdlib]

### Estimation des params
Comment calibrer depuis CSV historique (3 jours × 100k ticks).

### Diagnostic de succès
Quel signal mesurable sur backtest indique que le modèle fonctionne (au-delà du PnL brut).

### Risque / scénarios d'échec
Conditions de marché qui feraient exploser la stratégie.

### Originalité score (1-10)
Par rapport à ce qui a été testé (§3).
```

---

## 7. Ma commande exacte

**Propose-moi 8 idées** d'alpha, réparties :
- 2 idées de **microstructure théorique** (Hawkes, Kyle, Glosten-Milgrom, etc.)
- 2 idées de **statistique avancée** (cointegration, HMM, OU, etc.)
- 2 idées de **LOB dynamics** (OFI, queue priority, book pressure, etc.)
- 2 idées **non conventionnelles** / créatives (game theory, info theory, fractal, etc.)

**Critères de sélection** :
- Priorité aux idées implémentables en <3h
- Priorité aux idées qui complètent v31 plutôt que le remplacent
- Priorité aux idées avec diagnostic empirique clair
- Évite tout ce qui est déjà dans §3

**Pour chaque idée, donne-moi** :
1. Le nom technique précis (papier de référence si applicable)
2. La formulation mathématique complète (pas de hand-waving)
3. Le pseudo-code compact
4. La stratégie d'estimation depuis CSV
5. Le diagnostic empirique pour valider avant submit live
6. Les pièges identifiés

---

## 8. Bonus : questions ouvertes que je me pose

Si tu as des insights sur ces questions, réponds aussi :

1. **Pourquoi mon OBI signal ne bat pas v31 ?** Est-il dominé par le Kalman, ou sous-spécifié ?
2. **Y a-t-il une façon optimale de combiner MAKE + TAKE** dans un cadre unifié (HJB) ?
3. **Comment détecter si un bot adverse a un pattern exploitable** sans données d'identité ?
4. **Quel est le meilleur estimateur de volatilité intraday** pour un asset avec spread wide et sparse trades ?
5. **Comment pricer l'adverse selection** quand je pennyise le book (paye-je pour être picked off) ?
6. **Y a-t-il un framework unifié** entre Kalman (estimation FV) et Stoikov (optimal quotes) ?
7. **L'information asymétrique** entre rounds (les scores du board) peut-elle être exploitée ?

---

## Fin du briefing

Tu as le contexte complet. Je veux des idées **techniquement solides, originales, testables**. Pas de "try more features". Pas de "use machine learning". Du concret, du mathématique, du diagnostique.

**Go.**
