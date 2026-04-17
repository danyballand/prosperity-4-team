# HANDOFF.md — Onboarding complet Claude (ou nouvelle session)

**Lis ce document en entier avant toute action.** Il contient l'état complet du
projet IMC Prosperity 4 de Dany, ce qui a été fait, ce qui reste à faire, la
méthodologie, et les pièges à éviter. Il est conçu pour qu'une nouvelle
session Claude (ou un collaborateur humain) soit 100% opérationnel en 15-20 min
de lecture.

---

## 1. Qui est l'utilisateur et contexte

- **Nom** : Dany
- **Email** : danyedward.balland@gmail.com
- **Date de référence** : 17-18 avril 2026
- **Machine** : Mac (chemin : `/Users/danyballand/Documents/Dany Mac/TRading /Prosperity/`)
- **Langue de communication préférée** : français (mais accepte l'anglais dans code/docs)
- **Style de communication** : direct, concret, demande des chiffres, pas de bullshit ou d'enthousiasme artificiel. Apprécie la franchise sur l'incertitude.

### Compétition
- **IMC Prosperity 4** (avril 2026) — compétition de trading algorithmique par équipes
- **5 rounds** consécutifs, chaque round introduit de nouveaux produits et/ou mécaniques
- Les produits/stratégies de chaque round **continuent à scorer** sur tous les rounds suivants
- **Position limits par produit** (80 par produit R1)
- **Format** : 100,000 ticks (1000 snapshots à step=100) par jour, 3 jours de training + 1 jour live

### Équipe
- Dany joue en équipe de 2 avec un pote
- Le pote a commit les CSV data + tutorial sur GitHub
- Pas encore aligné sur la répartition des tâches R2

---

## 2. État actuel (post R1 submit, Round 2 imminent)

### Résultats R1 live
| Submit | PnL total | Osmium | Pepper |
|---|---:|---:|---:|
| **v31 (champion baseline)** | +12,159.00 | +4,716.00 | +7,443.00 |
| **v32 (submission 209060)** | +12,157.69 | +4,714.69 | +7,443.00 |

- **Top leaderboard** : ~+15,000 XIREC
- **Gap** : ~+3,000 (25%)
- **Delta v32 vs v31** : -1.31 XIREC (essentiellement noise — strictement identique)
- **Conclusion** : v32 n'apporte pas de gain live mais ne dégrade pas non plus

### Repo GitHub
- **URL** : https://github.com/danyballand/prosperity-4-team (PRIVATE)
- **Dernier commit** : `425aaee Reorganize into R1/ and R2/ subdirs with detailed READMEs`
- **Collaborateur** : le pote de Dany (a accès)

---

## 3. Structure du repo (à jour)

```
.
├── HANDOFF.md                  # CE DOCUMENT — onboarding complet
├── README.md                   # navigation centrale
│
├── R1/                         # Round 1 complet
│   ├── README.md               # narrative R1, architecture, backtester
│   ├── trader.py               # ★ v31 champion FROZEN (MD5: a45f0d686e53172163e08ef9dad0081c)
│   ├── trader_v32.py           # v32 = v31 + OFI Osm (MD5: 8cb7e489fe7bb5b260cb77921c1ae699)
│   ├── local_backtest_v3.py    # backtester calibré (Pep 99.6%, Osm 41%)
│   ├── datamodel.py            # fourni par IMC
│   ├── retest_with_v3.py       # harness A/B variantes v31 paramétriques
│   ├── retest_v32_addons.py    # harness A/B add-ons OFI/Toxicity/QueueSkip
│   ├── retest_v32_ofi_grid.py  # grid search OFI (α × halflife)
│   ├── data/                   # 6 CSV market data R1
│   ├── tutorial_data/          # 4 CSV tutorial round
│   └── rejected/               # stratégies testées et PERDANTES
│       ├── README.md           # explique chaque échec
│       ├── trader_stoikov.py (+84)
│       ├── trader_stoikov_v2.py (+12,015)
│       ├── trader_pep_bnh.py (-4,367)
│       ├── trader_signal_stack.py (-166,874)
│       ├── local_backtest.py   # v1 buggé (causal leak)
│       ├── local_backtest_v2.py # v2 buggé (overfill)
│       └── retest_with_v2.py
│
├── R2/                         # Round 2 préparation
│   ├── README.md               # quoi/pourquoi/comment
│   ├── R2_PLAYBOOK.md          # decision tree 180-min jour J
│   ├── analyze_r2.py           # 1-click analyse CSV (stats, corr, basket, ADF)
│   ├── r2_primitives.py        # building blocks (SpreadTrader, HardcodedMeanZ, swmid)
│   ├── trader_r2_template.py   # skeleton plug-and-play 3 templates
│   ├── datamodel.py
│   └── data/                   # (vide — à remplir à la release R2)
│
├── docs/                       # documentation cross-cutting
│   ├── PROMPT_BACKTEST_METHODOLOGY.md  # protocole audit 8 étapes
│   ├── PROMPT_OPUS_R2.md               # onboarding Opus 4.7 (avant handoff, mais à jour)
│   ├── PROMPT_ALPHA_RESEARCH.md
│   └── gemini_deep_research_prompt.md
│
└── archive/versions/           # historique trader_v1 → v30+
```

---

## 4. Architecture v31 (le champion — ne jamais modifier)

Le fichier `R1/trader.py` (MD5 `a45f0d686e53172163e08ef9dad0081c`) est
**FROZEN**. 800 lignes, stdlib Python uniquement.

### Produits R1

**ASH_COATED_OSMIUM** — stable mean-reverting autour 10,000
- Position limit : 80
- std mids : ~4.29 (très stable)
- Spread moyen : ~16 ticks
- Depth moyen : ~18 units/level

**INTARIAN_PEPPER_ROOT** — trending ~+1,000/jour
- Position limit : 80
- std mids : ~817 (volatile)
- Spread moyen : ~12 ticks
- Drift +52% du range

### Osmium — techniques (dans `trade_product`)

1. **FV fixe** à 10,000 (`fixed_fv`)
2. **Triple edge MAKE** : 3 niveaux de quotes à edge=97 (55% meilleur, 30% -1, 15% -2)
3. **Pennying** : si spread suffisant, améliorer d'1 tick tout en restant à min_edge
4. **Inventory clearing** : si |pos| > 20% limit, dump agressif via TAKE
5. **Inventory-aware take** : skew des seuils TAKE selon position

### Pepper — techniques

1. **Kalman FV** (`use_kalman: True`) avec drift=2.5, Q=0.25, R=200
2. **Bootstrap long** : dès tick 0, viser +80 en achetant sous `anchor + 9`
3. **Target bias decay** : position cible décroît de 30 → 0 linéairement
4. **Hold until 97%** : on garde la position long-biased jusqu'à 97% du jour
5. **Trend guard** : si momentum short/long MAs négatifs, cut le bias
6. **ID markout scoring** (shadow mode) : détecte bots informés par markout de trades

### Paramètres critiques (cliffs paramétriques)

- `make_edge Osm = 97` — testé : 95→+85, 100→-1,197 (cliff étroit)
- `bootstrap_cap_offset = 9` Pepper — testé 15→-1,230, 20→-2,450, 30→-4,180
- `max_bias = 30` Pep — testé 40→-85, 50→-240
- `clearing_threshold = 0.20 * limit`

### v32 = v31 + 1 add-on (OFI)

Seul ajout vs v31 :
- **OFI correction Osm** (Cont-Kukanov-Stoikov 2014) : α=2.0, halflife=50 ticks
- Flag `use_ofi_correction = True` sur Osmium
- Backtest 3j : +118 XIREC (mais day 0 delta = 0, gain concentré sur d-2)
- Live : -1.31 XIREC (noise)

v32 contient aussi toxicity tracker (jamais déclenché en live, harmless) et
queue-skip flag off (testé : -185 si activé).

---

## 5. Le backtester v3 — critique à comprendre

Fichier : `R1/local_backtest_v3.py`

### Pourquoi c'est crucial
Sans backtester fiable, aucune décision ne peut être validée. **Chaque tuning,
chaque variante, chaque submit passe par là.**

### Les 4 bugs corrigés vs v1/v2

| # | Bug | Symptôme | Fix appliqué |
|---|---|---|---|
| B1 | **Fuite causale** | Pepper backtest = 105% du live (impossible) | `market_trades[T]` sont signal, les fills passifs matchent `market_trades[T+1]` |
| B2 | **Book pas muté** | 2 ordres même niveau → chacun consomme 10u (overfill x2) | Mutation `depth.buy_orders`/`sell_orders` après chaque fill |
| B3 | **Cutoff off-by-one** | `ts > 100_000` inclut ts=100_000 → 1001 snapshots | Changé en `ts >= 100_000` (exactement 1000) |
| B4 | **Sweep cascade manquant** | Si pennyise 10009 et CSV trade 10010, 0 fill | Cascade : tout ordre nôtre à prix meilleur que tp est sweep first |

### Fidélité calibrée (validée contre live)

| Produit | Backtest day 0 | Live day 0 | Fidélité |
|---|---:|---:|---:|
| **Pepper** | +7,410 | +7,443 | **99.6%** ✓ fiable en absolu |
| **Osmium** | +1,931 | +4,716 | 41% (relatif seulement) |

### Pourquoi Osmium plafonne à 41%

Le CSV `trades_round_1_day_*.csv` ne contient que les trades **bot-to-bot**
visibles (~5% du vrai flow du marché). Le reste du PnL Osm vient du flow
**invisible** (fills passifs contre market orders non enregistrés dans le CSV).

### Règles d'usage

- **Pepper backtest** → confiance en absolu (+500 backtest ≈ +500 live)
- **Osmium backtest** → comparaison relative entre variantes OK, jamais extrapoler en absolu
- **Day 0 backtest** = meilleur proxy du live (confirmé par v32 : backtest d0=0 → live d0=-1.31)

### Exécution

```bash
cd R1/
python3 local_backtest_v3.py
# Doit donner exactement :
# GRAND TOTAL: +27653.0
#   ASH_COATED_OSMIUM  +5203.0
#   INTARIAN_PEPPER_ROOT  +22450.0
```

Si résultat différent → env cassé, ne pas continuer.

---

## 6. Méthodologie d'audit (8 étapes obligatoires)

Fichier : `docs/PROMPT_BACKTEST_METHODOLOGY.md`

**Chaque variante testée doit passer par ces 8 étapes.** Aucun raccourci.

1. **Sanity baseline** : `md5 R1/trader.py` = `a45f0d686e53172163e08ef9dad0081c` + `local_backtest_v3.py` = +27,653
2. **Variante en fichier séparé** : jamais éditer `trader.py` directement. Swap/test/restore.
3. **Sanity OFF-switch** : flag par défaut FALSE doit donner exactement +27,653 (sinon wiring cassé)
4. **Grid search** : sweep de paramètres, chercher **plateau** (5 valeurs voisines stables) pas pic isolé
5. **Sign-flip** : inverser le signe du signal. Si +α gagne et -α perd symétriquement → signal réel. Sinon = noise.
6. **Day-by-day** : décomposer delta sur d-2, d-1, d0. Si > 70% du gain vient d'1 jour = overfit.
7. **Verdict chiffré** avec tableau format strict (colonne baseline / variante / delta par produit × jour)
8. **Confiance** : BASSE / MOYENNE / HAUTE selon jour 0 delta + cohérence grid + sign-flip

### Seuils de décision

- Backtest Δ < 0.1% → noise, garde baseline
- 0.1% < Δ < 0.5% → décision = fidélité × risque asymétrique (Pep oui, Osm non sauf signal très fort)
- Δ > 0.5% → creuser, probablement réel

### Ce qu'on refuse

- Tests 1-jour seulement
- Modifs directes de `trader.py`
- "Looks good, submit" sans audit complet
- Skip du sign-flip sur signal directionnel
- Extrapolation live depuis backtest Osm en absolu

---

## 7. Stratégies R1 testées et rejetées

Voir `R1/rejected/README.md` pour détail complet. Résumé :

### Architectures entières rejetées

| Fichier | Idée | Backtest 3j | Leçon |
|---|---|---:|---|
| `trader_stoikov.py` | Avellaneda-Stoikov full formule | **+84** | T-t=100k ticks → reservation_price s'envole |
| `trader_stoikov_v2.py` | Stoikov avec drift_horizon=5 | **+12,015** | optimal_spread dévie de 20t vs l'optimum empirique 97t |
| `trader_pep_bnh.py` | Pure buy & hold Pepper | **-4,367** | Pas de MAKE pour compenser le spread payé |
| `trader_signal_stack.py` | 5 signaux empilés TAKE-only | **-166,874** | Friction TAKE tue les signaux |

### Variantes paramétriques rejetées (via `retest_with_v3.py`)

18+ variantes testées, toutes ≤ 0 vs v31. Conclusion : v31 est à son optimum
paramétrique local dans son espace.

### Add-ons v32 testés

| Add-on | Backtest | Verdict |
|---|---:|---|
| **OFI Osm** (α=2.0, hl=50) | **+118** (day 0 = 0) | Retenu mais marginal |
| Toxicity tracker (own markout) | 0 | Pas testable en backtest, harmless live |
| Queue-skip (pro-rata dilution) | -185 à 0 | Rejeté |

---

## 8. Préparation R2 (faite, prête à l'emploi)

### 3 templates pour les 3 formats historiques R2

| Round historique | Format | Template |
|---|---|---|
| **P1 2023 R2** | Pair cointegration (PINA/COCO ratio 15/8) | `PAIR_CONFIG` |
| **P2 2024 R2** | Cross-venue arbitrage (ORCHIDS + tariffs) | `CROSS_VENUE_CONFIG` |
| **P3 2025 R2** | Basket/ETF arb (PICNIC_BASKET 6C+3J+1D) | `BASKET_CONFIG` |

**⚠ Correction importante** : GIFT_BASKET = 4C+6S+1R était **P2 R3**, PAS P2 R2.
P2 R2 = ORCHIDS (cross-venue arb, attention aux features exogènes distractrices
comme sunlight/humidity).

### Outils R2 prêts

**`R2/analyze_r2.py`** — 1-click CSV analysis (< 30 sec) :
- Stats par produit (mean, std, drift, range)
- Order book characteristics (spread, depth)
- Matrice de corrélation
- Paires cointégrées (corrélation > 0.85, OLS)
- Baskets synthétiques (r² > 0.90 sur combinaisons 2/3/4 produits)
- ADF test (stationarity) + half-life OU
- Bot flow analysis
- Interprétation automatique

Usage :
```bash
cd R2/
python3 analyze_r2.py data/
# Ou sanity sur R1 :
python3 analyze_r2.py ../R1/data/
```

**`R2/r2_primitives.py`** — 10 building blocks :
- `HardcodedMeanZ` : **Z-score avec mean hardcodé** (approche Linear Utility, 99% des winners basket)
- `SpreadTrader` : pair trading avec entry/exit Z-thresholds
- `BasketPricer` : prix synthétique basket
- `RegimeDetector` : drift de slope
- `swmid` : size-weighted mid (formule Linear Utility)
- `safe_order` : clamp qty pour respect de position limit
- `ZScoreEWMA`, `multi_leg_orders`, `net_delta`, `suggest_hedge`

Self-test :
```bash
cd R2/
python3 r2_primitives.py
# Doit donner : === All primitives functional ===
```

**`R2/trader_r2_template.py`** — skeleton plug-and-play :
- Orchestrateur avec 3 templates (désactivés par défaut)
- Activation par flag `enabled: True` dans la config correspondante
- Inline primitives (single-file pour submit IMC)

### Playbook 180-min jour J

Fichier : `R2/R2_PLAYBOOK.md`

| Phase | Durée | Action |
|---|---|---|
| **T+0 à T+30** | 30 min | Download CSV, run `analyze_r2.py`, identifier structure |
| **T+30 à T+90** | 60 min | Activer template, remplir configs |
| **T+90 à T+150** | 60 min | Adapter backtester R2, grid search, méthodologie 8-étapes |
| **T+150 à T+180** | 30 min | Submit final |

**Règle** : si > 180 min → submit la version la plus simple qui marche.
Simple qui submit > parfait qui miss la deadline.

### Paramètres exacts des top teams (pour calibration)

**Linear Utility (P2 rank 2, basket)** :
```python
default_spread_mean = 379.50439988484239  # HARDCODED (pas rolling !)
spread_std_window   = 45                   # ROLLING court
zscore_threshold    = 7                    # (std court → gros z)
target_position     = 58                   # sur 60 (JAMAIS 100%)
```

**nicolassinott (P1 R2, pair)** :
```python
spread = P_PINA - (15/8) * P_COCO
entry_z = 1.5
exit_z  = 0.5
```

**Chrispyroberts (P3 7th, basket)** :
```python
zscore_threshold = 20
# Allocation : 100% Basket1 z-score, 60% Basket2 premium, 32% Basket2 z-score, 8% MM
```

---

## 9. Pièges confirmés à éviter

### Pour le code

1. **Position limit overshoot = rejet total** (pas clamp). CarterT27 P3 R2 a perdu pour ça. **Toujours** : `qty = min(desired, limit - pos)`
2. **Rolling_mean sur spread persistant** → converge vers prix courant → z-score petit → 0 trade. **Hardcode le mean**.
3. **TraderData limit 49k chars** → trimmer history buffers en fin de run
4. **Over-fit 3 jours CSV** → Matius Chong P3 a eu R2 OK, R5 catastrophique
5. **TAKE-only stratégie** → friction mange tout le signal (notre signal_stack -166k)
6. **Features exogènes séduisantes** (sunlight, humidity P2 R2) → distractions, vraie alpha est ailleurs

### Pour la méthodologie

1. **Backtest 1 jour** = insuffisant, minimum 3 jours
2. **Modif directe `trader.py`** = interdit, toujours swap/test/restore
3. **Skip du sign-flip** sur signal directionnel = accepter du noise comme signal
4. **Extrapolation live depuis Osm backtest en absolu** = faux (41% fidélité)
5. **Submit sans day-by-day decomposition** = risque d'overfit day-specific

### Pour l'équipe

1. **Décider AVANT le round qui a le dernier mot** sur le submit — pour éviter la dispute 10 min avant deadline
2. **Changer le code 30 min avant submit** = cause #1 de catastrophe
3. **Chacun dans son coin sans sync** = double travail
4. **Activer plusieurs templates R2 en même temps** = risque multi-leg explosif

---

## 10. Commandes clés à connaître

### Sanity check environnement
```bash
cd "/Users/danyballand/Documents/Dany Mac/TRading /Prosperity"
md5 R1/trader.py
# DOIT : a45f0d686e53172163e08ef9dad0081c

cd R1 && python3 local_backtest_v3.py
# DOIT : GRAND TOTAL: +27653.0

cd ../R2 && python3 r2_primitives.py
# DOIT : === All primitives functional ===
```

### Tester une variante v31
```bash
cd R1/
cp trader.py trader_backup.py
cp trader_<variante>.py trader.py
python3 local_backtest_v3.py
cp trader_backup.py trader.py
md5 trader.py  # doit redonner a45f0d686e53172163e08ef9dad0081c
rm trader_backup.py
```

### Analyser CSV R2 à la release
```bash
cd R2/
# Quand les CSV R2 arrivent :
cp ~/Downloads/*round_2* data/
python3 analyze_r2.py data/
# Lire : R2_ANALYSIS_REPORT.md
```

### Git workflow
```bash
git pull origin main
git checkout -b r2-<feature>
# ... modifs ...
git add . && git commit -m "..."
git push origin r2-<feature>
# PR + review par binôme avant merge vers main
```

---

## 11. Ce qui reste à faire / décisions en attente

### Avant R2 (ce soir / demain matin)

- [ ] Dany doit caller son pote pour aligner les rôles
- [ ] Décider qui a le **dernier mot** sur le submit R2
- [ ] Setup canal Discord/Slack + Google Doc live
- [ ] Pote doit lire R2/README.md + R2_PLAYBOOK.md
- [ ] Pote doit vérifier env (md5, backtest +27,653)

### Stratégies split possibles

**Option A (recommandée)** : split par produit
- Dany : Osmium R1 + infra backtester + template R2 principal
- Pote : Pepper R1 + analyse CSV R2 + recherche signal + manual trading

**Option B** : split par phase
- Un fait dev/infra, l'autre fait analyse/calibration/review

**Option C** : split par approche
- Chacun code sa solution R2 en parallèle, on compare backtests, on garde la meilleure

### Ce qui pourrait être fait mais pas prioritaire

1. Adapter `local_backtest_v3.py` pour R2 (changer PRODUCTS et DATA_DIR selon les CSV R2)
2. Créer un script de calibration offline automatique (calcule spread_mean pour chaque formule de basket candidate)
3. Tester d'autres halflives sur OFI (grid search déjà fait, mais plus fin)
4. Implémenter un kill-switch PnL dans `trader.py` (flatten tout si drawdown > X)

---

## 12. Personnalité / préférences de Dany

- Français, ton direct et franc
- Ne veut pas d'enthousiasme artificiel (« looks good, ship it »)
- Demande des chiffres pour chaque claim
- Demande honnêteté sur l'incertitude (si on ne sait pas, on le dit)
- Apprécie les tableaux markdown avec deltas chiffrés
- Adopte les décisions basées sur des tests chiffrés, pas des opinions
- Feedback direct : « tu es sur que c'est l'optimum ? » — il remet en question, sait demander plus
- Efficace en parallèle — préfère que Claude lance plusieurs choses en parallel plutôt que séquentiel quand possible

---

## 13. Historique complet des interactions (résumé chronologique)

Pour référence, voici ce qui s'est passé dans cette session Claude :

1. **Point de départ** : Dany venait de scorer +12,159 R1 avec v31. Top leaderboard ~+15k.
2. **Tentative Stoikov** : testé trader_stoikov.py et v2 → catastrophe (+84 et +12k vs +27k)
3. **Audit du backtester** : découverte de 4 bugs critiques (causal leak, overfill, cutoff, sweep). Correction → v3 calibré 99.6% Pep.
4. **Test architectures alternatives** : 4 testées, toutes pires que v31.
5. **Création PROMPT_OPUS_R2.md** : onboarding pour futur Claude sur R2.
6. **Création PROMPT_ALPHA_RESEARCH.md** : recherche d'alpha offline.
7. **Recherche alpha IA** : 8 idées générées (OFI, toxicity, queue inference, Glosten-Milgrom, VECM, HMM, Kelly+GARCH, sweep detection).
8. **Test des 3 add-ons v32** : OFI Osm retenu (+118 backtest), toxicity harmless, queue-skip rejeté.
9. **Submit v32** (submission 209060) : live = +12,157.69 = -1.31 vs v31 (noise, prédit par backtest day 0 = 0).
10. **Diagnostic post-submit** : 0 erreur, OWNMO tous positifs (+2 à +8 ticks, pas d'adverse selection).
11. **Création PROMPT_BACKTEST_METHODOLOGY.md** : protocole 8 étapes.
12. **Préparation R2** : analyze_r2.py, r2_primitives.py, trader_r2_template.py, R2_PLAYBOOK.md.
13. **Recherche web top teams R2** : Linear Utility, nicolassinott, Chrispyroberts, etc. Correction : GIFT_BASKET = P2 R3, pas R2.
14. **Setup GitHub** : repo privé, init, commit, push, merge avec commits du pote.
15. **Reorganisation en R1/ et R2/** : structure finale avec 3 READMEs détaillés.

---

## 14. Si tu reprends cette session en tant que Claude

### Ce que tu dois confirmer avant d'agir

1. Lis `README.md` du repo (2 min)
2. Lis `R1/README.md` (5 min) — contexte R1
3. Lis `R2/README.md` (5 min) — préparation R2
4. Lis `R2/R2_PLAYBOOK.md` (5 min) — plan jour J
5. Lis `docs/PROMPT_BACKTEST_METHODOLOGY.md` (3 min) — protocole

### Commandes à exécuter pour vérifier l'état

```bash
cd "/Users/danyballand/Documents/Dany Mac/TRading /Prosperity"

# 1. MD5 champion
md5 R1/trader.py   # doit = a45f0d686e53172163e08ef9dad0081c

# 2. Backtest sanity
cd R1 && python3 local_backtest_v3.py | tail -5
# doit = GRAND TOTAL: +27653.0

# 3. Primitives R2
cd ../R2 && python3 r2_primitives.py | tail -2
# doit = All primitives functional

# 4. Analyse R2 sur R1 (sanity)
python3 analyze_r2.py ../R1/data/ | tail -5
# doit identifier Osm stable et Pep trending
```

### Si tout OK → tu es prêt

Demande à Dany :
1. Est-ce que R2 a démarré ? Si oui, où sont les CSV ?
2. Quel format R2 ? (pair / basket / cross-venue / autre ?)
3. Est-ce qu'il a aligné les rôles avec son pote ?
4. Y'a-t-il une décision en attente de sa part ?

### Si quelque chose ne va pas

- Si MD5 différent → quelqu'un a modifié trader.py, `git checkout R1/trader.py` pour restaurer
- Si backtest != +27,653 → env cassé, investiguer (Python version ? CSV corrompus ?)
- Si primitives foirent → bug introduit récemment, `git log R2/r2_primitives.py` pour identifier

---

## 15. Références externes utiles

### Top teams repos (à consulter si bloqué)

- https://github.com/ericcccsliu/imc-prosperity-2 (P2 #2, basket params exacts)
- https://github.com/chrispyroberts/imc-prosperity-3 (P3 #7 global)
- https://github.com/Sylvain-Topeza/imc-prosperity-3 (P3 top 1%)
- https://github.com/CarterT27/imc-prosperity-3 (P3 #9, post-mortem position limit)
- https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal (P1 #2)
- https://github.com/nicolassinott/IMC_Prosperity (P1, z=±1.5)
- https://github.com/jmerle/imc-prosperity-2 (P2 #9, code clean)
- https://github.com/pe049395/IMC-Prosperity-2024 (P2 #13, "trade basket only")
- https://github.com/jmerle/imc-prosperity-2-backtester (backtester officieux)
- https://github.com/jmerle/imc-prosperity-3-backtester (backtester P3)

### Papers pertinents

- **Cont, Kukanov, Stoikov (2014)** — Order Flow Imbalance, basis de notre OFI addon
- **Avellaneda & Stoikov (2008)** — market making, testé et rejeté (T-t problem)
- **Glosten & Milgrom (1985)** — Bayesian FV update, pas implémenté
- **Engle & Granger (1987)** — cointegration test (utilisé dans analyze_r2.py ADF)

---

## 16. FAQ rapide

**Q : Est-ce qu'on peut remettre v31 en production si v32 a posé souci ?**
R : Oui. `cp R1/trader.py <endroit>` et uploader sur IMC. v31 est intact, MD5 `a45f0d686e53172163e08ef9dad0081c`.

**Q : Le backtester marche-t-il pour R2 directement ?**
R : Non, il faut adapter `R1/local_backtest_v3.py` (changer PRODUCTS et DATA_DIR) ou créer `R2/local_backtest_r2.py`. À faire le jour J.

**Q : Peut-on tester v32 de manière plus agressive ?**
R : Oui, mais les variantes paramétriques testées sont toutes pires que v31 actuel. Les add-ons sur `trader_v32.py` (toxicity, queue-skip) restent disponibles via flags — les activer sans précaution peut dégrader.

**Q : Que faire si R2 est un format inattendu (pas pair/basket/cross-venue) ?**
R : Tomber sur du marché making étendu ou un format nouveau. Dans ce cas :
1. Run `analyze_r2.py` pour identifier les patterns
2. Adapter un des 3 templates comme base
3. Ou écrire une 4e template en suivant la structure de `trader_r2_template.py`

**Q : Dany veut que Claude code rapidement sans audit ?**
R : Non, même sous pression Dany préfère la méthodologie. Ne jamais skip les 8 étapes pour gagner du temps. Un bad submit en live coûte plus cher en XIREC qu'un submit tardif avec le bon résultat.

**Q : Le pote a commit quelque chose qui semble casser le backtester ?**
R : Restore la version main : `git checkout origin/main -- R1/trader.py R1/local_backtest_v3.py`. Puis investiguer le commit du pote via `git log --oneline` et caller Dany.

---

## Fin du handoff

Document maintenu à jour jusqu'au 17 avril 2026 ~13h (avant R2). Après R2,
mettre à jour la section 2 (résultats live) et la section 13 (historique).
