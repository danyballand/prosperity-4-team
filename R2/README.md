# Round 2 — préparation complète

**Statut** : Round 2 démarre aujourd'hui (18 avril 2026). Tout ce qui est
dans ce dossier a été préparé EN AMONT pour qu'on puisse, au moment où les
CSV R2 sortent, passer directement à l'action sans se réinventer.

**Temps cible release → submit : 180 minutes.** Ce dossier contient l'arsenal
pour tenir ce délai.

---

## 1. Pourquoi cette préparation ?

### Le problème
Round 2 IMC introduit toujours des **produits structurés** (relations
statistiques entre produits, arbitrages multi-leg). Les équipes qui scorent
le mieux sont celles qui :

1. **Identifient la structure rapidement** (5-30 min après release CSV)
2. **Ont les primitives déjà codées** (pas à les écrire sous stress)
3. **Ont un protocole de validation** (pas à improviser la méthodologie)
4. **Savent ce qui NE marche PAS** (pas à retenter des trucs déjà écartés)

### Notre solution
On a préparé 3 **templates de stratégie** couvrant les 3 formats historiques R2 :

| Format historique | Année | Template correspondant |
|---|---|---|
| **Pair cointegration** (PINA/COCO ratio 15/8) | P1 2023 | `PAIR_CONFIG` dans `trader_r2_template.py` |
| **Cross-venue arbitrage** (ORCHIDS, tariffs) | P2 2024 | `CROSS_VENUE_CONFIG` |
| **Basket / ETF arb** (PICNIC_BASKET 6C+3J+1D) | P3 2025 | `BASKET_CONFIG` |

Les 3 templates sont **désactivés par défaut**. Quand les CSV R2 sortent, on
identifie le format via `analyze_r2.py`, on active le template correspondant,
on remplit les configs (paramètres numériques), on backteste, on submit.

---

## 2. Structure du dossier

```
R2/
├── README.md                 # ce fichier
├── R2_PLAYBOOK.md            # ★ DECISION TREE 180-min à ouvrir le jour J
├── analyze_r2.py             # ★ 1-click analyse CSV (stats, corr, basket, ADF)
├── r2_primitives.py          # ★ building blocks testés
├── trader_r2_template.py     # ★ skeleton plug-and-play avec 3 templates
├── datamodel.py              # fourni par IMC (pour imports)
└── data/                     # CSV R2 (à remplir dès release — vide pour l'instant)
```

---

## 3. Les 3 outils — que font-ils, pourquoi ?

### 3.1 `analyze_r2.py` — le diagnostic automatique

**Quoi** : charge tous les CSV d'un dossier et produit un rapport markdown
complet en < 30 sec.

**Pourquoi** : la phase 1 (reconnaissance) est **toute** la bataille. Si on
rate l'identification de la structure, le reste ne peut pas sauver. Cet outil
élimine le risque humain.

**Ce qu'il détecte** :

1. **Stats par produit** : mean, std, drift, range
2. **Order book characteristics** : spread moyen, profondeur bid/ask
3. **Matrice de corrélation** des mids
4. **Paires cointégrées** (corrélation > 0.85) avec OLS `y = a + b·x`
5. **Baskets synthétiques** (r² > 0.90 sur combinaisons de 2/3/4 produits)
6. **ADF test** (stationarity proxy) sur les spreads
7. **Half-life Ornstein-Uhlenbeck** (vitesse de mean-reversion)
8. **Bot / flow analysis** (si CSV trades disponible)
9. **Interprétation automatique** : produits stables / trending / volatiles

**Usage** :
```bash
cd R2/
# Quand les CSV R2 arrivent, copier dans data/ :
cp ~/Downloads/*round_2* data/
# Puis :
python3 analyze_r2.py data/
# Output : R2_ANALYSIS_REPORT.md + print stdout
```

**Test sur R1** (pour valider que l'outil marche) :
```bash
python3 analyze_r2.py ../R1/data/
```
Doit sortir : "Osmium stable (fv≈10000)" + "Pepper trending (+52% range)".

### 3.2 `r2_primitives.py` — les building blocks

**Quoi** : 10 classes / fonctions testées + self-test intégré.

**Pourquoi** : ne pas coder les primitives sous stress au moment du R2. Tous
les patterns identifiés dans les writeups des top teams sont déjà disponibles
en code stdlib Python.

**Ce qu'il contient** :

| Primitive | Rôle | Inspiration |
|---|---|---|
| `ZScoreEWMA` | Z-score avec EWMA mean/std | Standard |
| `HardcodedMeanZ` | **Z-score avec mean hardcodé** + std rolling court (45 ticks) | Linear Utility (P2 rank 2) — 99% des top teams R2 basket |
| `SpreadTrader` | Signal de pair trading avec entry/exit Z-thresholds | nicolassinott (P1 R2) |
| `BasketPricer` | Prix synthétique basket = intercept + Σ poids·mids | Standard ETF arb |
| `RegimeDetector` | Détecte drift de slope sur rolling OLS | Custom |
| `swmid` | **Size-weighted mid** (formule Linear Utility) | Linear Utility |
| `safe_order` | Clamp qty pour respecter position limit | Leçon CarterT27 |
| `multi_leg_orders` | Place des ordres simultanés sur N legs | Standard |
| `net_delta` / `suggest_hedge` | Tracker d'exposition nette portefeuille | Standard |

**Pourquoi `HardcodedMeanZ` est critique** :

Un rolling_mean classique **converge vers le prix courant** quand le spread
persiste → le z-score ne spike jamais → **0 trade**. Linear Utility (rank 2
P2) a compris ça et utilisait :
```
default_spread_mean = 379.50439988484239   # HARDCODÉ depuis offline CSV
spread_std_window   = 45                    # rolling court (bruité = feature)
zscore_threshold    = 7                     # gros car std bruité
target_position     = 58/60                 # jamais 60/60 (position limit)
```

**Test** :
```bash
cd R2/
python3 r2_primitives.py
# Doit donner : === All primitives functional ===
```

### 3.3 `trader_r2_template.py` — le skeleton plug-and-play

**Quoi** : structure `class Trader` complète avec 3 templates de stratégie et
un orchestrateur qui appelle le bon selon les flags.

**Pourquoi** : on veut pouvoir activer **uniquement** la bonne stratégie une
fois la structure R2 identifiée, sans réécrire le squelette.

**Comment ça s'utilise** (exemple basket) :

1. Après `analyze_r2.py`, si on détecte "BASKET détecté : X = 6·A + 3·B + 1·C
   avec r²=0.95, spread_mean=380, spread_std=75", on va dans le fichier et on
   remplit :

```python
BASKET_CONFIG = {
    "enabled": True,                              # ← activer
    "basket": "PICNIC_BASKET1",
    "components": {"A": 6, "B": 3, "C": 1},
    "intercept": 0.0,
    "spread_mean": 379.50,                        # ← HARDCODÉ offline
    "z_window": 45,
    "entry_z": 7.0,                               # ← Linear Utility standard
    "exit_z": 2.0,
    "target_basket_pos": 58,                      # ← 58/60 (pas 60/60)
    "hedge_components": False,
}
```

2. Laisser les 2 autres templates `enabled: False`.

3. Run `local_backtest_v3.py` adapté pour R2 (à créer ou adapter depuis R1)
   pour valider.

4. Submit.

**Les templates** :

- `trade_pair(state, trader_data, cfg)` → pair cointegration via Z-score
- `trade_basket(state, trader_data, cfg)` → basket / ETF arb
- `trade_cross_venue(state, trader_data, cfg)` → ORCHIDS-like avec conversions

---

## 4. Le backtester — pourquoi on ne peut pas s'en passer

### C'est le fil rouge de toute la méthodologie

Chaque décision de submit, chaque tuning de paramètre, chaque choix de
seuil doit passer par le backtester. **Sans backtester fiable, tu joues à
la roulette.**

### Rappel des 4 bugs corrigés (v3, calibrée sur R1)

Voir `../R1/README.md` section 4 pour le détail. En résumé :

1. **Fuite causale** (B1) : market_trades[T] matche nos orders T+1, pas T
2. **Book non-muté** (B2) : chaque fill décrémente `depth.buy_orders`/`sell_orders`
3. **Cutoff strict** (B3) : `ts >= 100_000` (exactement 1000 snapshots)
4. **Sweep cascade** (B4) : tous ordres à prix ≥ trade-price sont sweepés first

### Fidélité établie sur R1

| Produit | Fidélité |
|---|---|
| Pepper | **99.6%** (absolu ≈ live) |
| Osmium | 41% (relatif OK, absolu trompeur) |

### Pour R2 : attention, il faut le ré-adapter

`R1/local_backtest_v3.py` charge :
- `data/prices_round_1_day_*.csv` (format spécifique R1)
- Produits hardcodés : `ASH_COATED_OSMIUM, INTARIAN_PEPPER_ROOT`

**Pour R2**, il faudra :
1. Charger `R2/data/prices_round_2_day_*.csv`
2. Adapter la liste `PRODUCTS` aux produits R2
3. Adapter `LIVE_DURATION_TS` si le round a un autre nombre de ticks

**Le script de test des templates** sera quelque chose comme (à créer le jour J) :
```python
# R2/local_backtest_r2.py (à créer)
# Copier R1/local_backtest_v3.py, changer PRODUCTS et DATA_DIR
# Importer trader_r2_template comme trader
```

### Pourquoi c'est critique pour R2

Un backtester fiable en R2 nous dira :
- **Si notre template + config donne PnL > 0** sur les jours de training
- **Si le day 0 (le plus récent, le plus proche du live) est positif**
- **Si le signal est robuste** (grid search, sign-flip, day-by-day)

Sans ça, on submit à l'aveugle. **Le v32 live +12,157 ≈ backtest +12k prouve
que notre backtester est honnête** — on peut lui faire confiance.

---

## 5. La méthodologie d'audit (obligatoire)

Voir `../docs/PROMPT_BACKTEST_METHODOLOGY.md` — protocole en **8 étapes** :

1. Sanity baseline (MD5 + PnL attendu)
2. Créer la variante dans un fichier séparé
3. Swap → test → restore (contrôle fortifié)
4. Sanity OFF-switch (flag off = baseline exact)
5. Grid search (plateau stable, pas pic isolé)
6. Sign-flip (signal directionnel validé)
7. Day-by-day decomposition (pas de gain concentré sur 1 jour)
8. Verdict chiffré avec confiance BASSE / MOYENNE / HAUTE

**Respecter cette méthodologie est la différence entre submit +500 XIREC
ou submit -2,000 XIREC.** Plusieurs de nos essais R1 qui semblaient bons
en backtest ont été éliminés par l'étape 5 (pic isolé = overfit) ou 6
(sign-flip échoué = noise).

---

## 6. Le playbook jour J — 180 minutes chrono

Voir `R2_PLAYBOOK.md` pour le détail minute par minute. Résumé :

| Phase | Durée | Action |
|---|---|---|
| **T+0 à T+30** | 30 min | Download CSV, run `analyze_r2.py`, identifier structure |
| **T+30 à T+90** | 60 min | Activer template, remplir configs (paramètres depuis rapport) |
| **T+90 à T+150** | 60 min | Adapter backtester R2, grid search, méthodologie 8-étapes |
| **T+150 à T+180** | 30 min | Submit final (trader.py ou template concaté) |

**Si on dépasse 180 min → submit la version la plus simple qui marche.** Le
"simple qui submit" > le "parfait qui miss la deadline".

---

## 7. Paramètres exacts des top teams (pour calibration)

### Linear Utility (P2 rank 2, basket P2 R3)
```python
default_spread_mean = 379.50439988484239    # HARDCODED offline
spread_std_window   = 45                     # ROLLING short (noisy = good)
zscore_threshold    = 7                      # ENTRY
target_position     = 58                     # sur limit 60 (NEVER 60/60)
swmid = (bb*ask_vol + ba*bid_vol) / (bid_vol + ask_vol)
```

### nicolassinott (P1 R2, pair PINA/COCO)
```python
spread = P_PINA - (15/8) * P_COCO
entry_z = 1.5
exit_z  = 0.5
```

### Chrispyroberts (P3 7th global, basket PICNIC_BASKET)
```python
zscore_threshold = 20          # std court = très bruyant
# Allocation :
#   100% limit Basket1 via z-score
#   60% limit Basket2 via premium differential
#   32% Basket2 via z-score
#   8%  MM passif sur spreads
```

---

## 8. Anti-patterns à éviter (leçons des autres R2)

| Erreur | Conséquence | Qui a fait l'erreur |
|---|---|---|
| **Rolling_mean au lieu de hardcoded** | Z-score jamais élevé → 0 trade | Plusieurs teams mid-tier |
| **target_position = 100% limit** | Order rejeté → strat morte | CarterT27 (P3 #9) |
| **Over-fit sur 3 jours CSV** | R2 OK mais R5 catastrophique | Matius Chong (P3) |
| **Trader tous les legs à market** | Slippage x10, perte d'edge | Teams qui ont hedgé fullly |
| **Suivre les features exogènes** (sunlight, humidity) | Distractions → rate l'alpha réelle | Teams P2 R2 |
| **Changer le code 30 min avant deadline** | Bugs → catastrophe | Cause #1 d'échec R2 |

---

## 9. Workflow git pour R2

### Branches recommandées
```
main                      # submit-able à tout moment
├── r2-analysis           # branche où ton pote run analyze_r2 et iterate
├── r2-pair               # si structure = pair
├── r2-basket             # si structure = basket
└── r2-cross-venue        # si structure = cross-venue
```

### Règle d'or
**Merge vers `main` seulement après backtest > baseline ET méthodologie 8-étapes
validée.** Aucun submit depuis une branche expérimentale.

---

## 10. Pour démarrer (checklist ce soir / demain matin)

- [ ] Lire **tout** `R2_PLAYBOOK.md` (15 min)
- [ ] Run `python3 analyze_r2.py ../R1/data/` → verify tool works
- [ ] Run `python3 r2_primitives.py` → All primitives functional
- [ ] Vérifier que `../R1/local_backtest_v3.py` donne encore +27,653
- [ ] Caller le binôme pour aligner rôles (split produit / phase / approche)
- [ ] Décider **qui a le dernier mot** sur le submit final
- [ ] Préparer Discord/Slack + Google Doc live
- [ ] Dormir

Demain matin quand les CSV arrivent :
1. `cp ~/Downloads/*round_2* R2/data/`
2. `python3 R2/analyze_r2.py R2/data/`
3. Ouvrir `R2_PLAYBOOK.md` phase 1
4. Go

---

## Fin

**Principe directeur** : la préparation, c'est 80% du résultat en R2. On a fait
notre part. Demain, on exécute proprement.
