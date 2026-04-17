# Round 2 — en cours

**Statut** (20 avril 2026) : R2 en cours, submit final **`trader_r2_v3_mega.py`**
(side channel id_markout Osm + bid MAF 500). Deadline dans quelques heures.

---

## 🎯 État actuel

**R2 s'est avéré être une extension de R1, PAS un nouveau format** (pair/basket/cross-venue).

- Mêmes produits : ASH_COATED_OSMIUM + INTARIAN_PEPPER_ROOT
- Mêmes position limits (80)
- NEW : MAF bid (top 50% → +25% volume)
- NEW : Manual Invest challenge (Research/Scale/Speed budget 50k)

**→ Les 3 templates préparés EN AMONT (pair/basket/cross-venue) n'ont PAS servi pour l'algo.**

### Submit final : `trader_r2_v3_mega.py`

Après **9 submits IMC** et **3 jours d'exploration**, le gain incrémental vs baseline est :

| | Baseline v31 | v3_mega final |
|---|---:|---:|
| Live R2 day 0 attendu | ~9,302 | ~**10,726** |
| **Delta** | | **+1,424 XIREC** |

**Découverte-clé : side channel `id_markout` sur Osmium** — ajouter ce flag cause un gain reproductible de +1,011 XIREC, même si le détecteur ne se déclenche jamais en simulation IMC (bot IDs vides). Effet binaire, non-directionnel (sign-flip test confirme).

Voir [`EXPLORATION.md`](EXPLORATION.md) pour le journal complet de l'analyse.

### Manual challenge

Allocation soumise : **Research=15% / Scale=45% / Speed=40%** (optimum math calculé via `optim_manual.py`).

- EV pessimistic : +140k XIREC
- EV median : +190k XIREC
- EV optimistic : +290k XIREC

---

## 📁 Préparation EN AMONT (conservée pour référence / R3)

Tout ce qui est dans ce dossier a été préparé avant release R2 pour passer à l'action en 180 min.
**Ces outils restent utiles pour R3-R5** si nouveaux formats.

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

### Fichiers actifs (submit final R2)

```
R2/
├── README.md                      # ce fichier
├── EXPLORATION.md                 # ★ journal complet 3j d'exploration algo
├── POSTMORTEM_R2.md               # ★ template à remplir post-results
│
├── trader_r2_v3_mega.py           # ⭐ SUBMIT FINAL R2 (side channel + bid 500)
├── trader_r2.py                   # v31 + bid 300 (baseline submit initial 276310)
├── optim_manual.py                # Grid search allocation R/S/Speed (→ 15/45/40)
│
└── data/                          # CSV R2 (copiés depuis Downloads/)
```

### Variantes traders explorées

```
R2/
├── trader_r2_v2.py                # v31 + Pepper cycling rolling MA (échec: -1,381)
├── trader_r2_v3a.py               # v31 + id_markout Osm bid 300 (découverte: +1,011)
├── trader_r2_v3b.py               # v31 + bid MAF agressif 1000 (non submit)
├── trader_r2_v3c.py               # v3a + bid 500 (submit 279306)
├── trader_r2_v3_reverse.py        # v3a sign-flip test (confirme side channel)
├── trader_r2_v3_amplified.py      # v3a + 3× calls (plateau confirmé)
├── trader_r2_v4.py                # v31 + Pepper snap-back Codex (échec: -525)
└── trader_r2_probe.py             # v31 + enhanced logging (non submit, diagnostic)
```

### Scripts d'analyse

```
R2/
├── local_backtest_r2.py           # Backtester v3 adapté R2 (validated Pep 99.6%, Osm 41%)
├── local_backtest_r2_maf.py       # Backtester + simulation MAF +25% volume
├── grid_search_r2.py              # Grid params v31 (make_edge, bootstrap, skew...)
├── grid_search_features.py        # Grid features (OBI, adaptive_fv, kalman...)
├── grid_triple_edge.py            # Test ratios triple_edge via monkey-patch
├── grid_cycling.py                # Grid Pepper cycling (v2)
├── grid_v4_snapback.py            # Grid Pepper snap-back (v4)
├── verify_codex_signals.py        # Validation signaux Codex
├── analyze_imc_logs.py            # Parser logs IMC multi-submits
└── analyze_r2.py                  # Script original 1-click CSV stats
```

### Toolkit préparé EN AMONT (conservé pour R3-R5)

```
R2/
├── R2_PLAYBOOK.md                 # DECISION TREE 180-min pour nouveau format
├── r2_primitives.py               # Building blocks (SpreadTrader, HardcodedMeanZ, swmid...)
├── trader_r2_template.py          # Skeleton 3 templates (pair/basket/cross-venue) — NON UTILISÉ R2
└── datamodel.py                   # fourni par IMC
```

**Recherche d'alpha offline** (dans `../docs/`) — prompts Gemini Deep Research +
rapports générés. Voir § 11 pour la stratégie d'exploitation :

```
docs/
├── PROMPT_GEMINI_R2_PAIR_TRADING.md        # prompt spécifique pair
├── PROMPT_GEMINI_R2_CROSS_VENUE.md         # prompt spécifique cross-venue
├── PROMPT_GEMINI_R2_BASKET_ARB.md          # prompt spécifique basket
├── PROMPT_GEMINI_R2_META_POSTMORTEMS.md    # prompt meta (échecs/réussites R2)
├── Analyse Stratégique Pair Trading IMC Prosperity.pdf   # rapport Gemini ✓
├── Analyse Cross-Venue Arbitrage ORCHIDS P2.pdf          # rapport Gemini ✓
├── Analyse Stratégie Basket Arbitrage P3.pdf             # rapport Gemini ✓
└── Analyse des Échecs IMC Prosperity Round 2.pdf         # rapport Gemini meta ✓
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
- [ ] **Lire les 4 rapports Gemini** (`docs/Analyse *.pdf`) — au moins l'exec summary de chaque + les sections params exacts (15 min/rapport, ~60 min total)
- [ ] Extraire de chaque PDF les **params de départ** (hardcoded mean, z-thresholds, position caps) et les **pièges confirmés** → coller dans `R2_PLAYBOOK.md` section calibration
- [ ] Du rapport **Échecs R2** : extraire la **checklist pré-submit** (≥15 items) → coller dans `R2_PLAYBOOK.md` section finale
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

## 11. Recherche d'alpha offline — stratégie Gemini Deep Research

### Pourquoi on a fait ça

Notre backtester donne la fidélité sur **ce que notre code fait**, pas sur
**ce que les autres teams ont fait**. Pour combler notre gap de ~3k vs top R1
et ne pas répéter leurs erreurs en R2, on a besoin de **compétitive intelligence**
sur les 3 éditions précédentes (P1 2023, P2 2024, P3 2025).

On a donc préparé **4 prompts Gemini Deep Research** (dans `../docs/`) qui
tournent en parallèle et produisent des rapports exhaustifs, chacun focalisé
sur un format R2 historique ou une dimension transversale. **Les 4 rapports
sont générés** (PDF dans `../docs/`) et prêts à être exploités.

### Les 4 prompts

| # | Fichier | Objet | Priorité info |
|---|---|---|---|
| 1 | `PROMPT_GEMINI_R2_PAIR_TRADING.md` | P1 2023 PINA/COCO | Params exacts ratios/z + variantes rejetées + gestion multi-leg |
| 2 | `PROMPT_GEMINI_R2_CROSS_VENUE.md` | P2 2024 ORCHIDS | Mécanique `conversions`+tariffs + preuve chiffrée features exogènes = bruit |
| 3 | `PROMPT_GEMINI_R2_BASKET_ARB.md` | P3 2025 PICNIC_BASKET | Hardcoded vs rolling mean chiffré + formule multi-leg clamp |
| 4 | `PROMPT_GEMINI_R2_META_POSTMORTEMS.md` | Toutes éditions | 25+ crashes R2 chiffrés + checklist pré-submit |

### Pourquoi **4 prompts spécifiques** et pas 1 général

Gemini Deep Research sur un scope trop large produit 30 pages de fluff dilué.
Les 3 formats historiques R2 sont **radicalement différents** (pair vs
cross-venue vs basket) — techniques, paramètres exacts et pièges n'ont rien
en commun. 4 rapports indépendants = jour J, on lit celui qui match le format
observé après 30 min d'`analyze_r2.py`, plus le meta en transverse.

### Cadrage anti-confusion intégré aux prompts

Chaque prompt référence explicitement les pièges de cadrage Gemini :
- GIFT_BASKET (4C+6S+1R) = **P2 R3**, pas P2 R2 ni P3 R2
- P2 R2 = ORCHIDS cross-venue (pas un basket)
- P3 R2 = PICNIC_BASKET (pas un pair)
- Linear Utility = P2 #2 ; leur hardcoded mean `379.50439988484239` concerne le
  basket P2 R3, pas P3 R2 — à **recalibrer** sur les CSV R2 2026

Chaque prompt demande aussi : **code réel > README**, **citation fichier+ligne**,
**dire "non trouvé" plutôt qu'inventer un chiffre**.

### Livrables attendus de chaque rapport

Commun aux 3 rapports spécifiques (pair / cross-venue / basket) :
1. Exploration ≥ 10 repos GitHub de l'édition ciblée
2. Tableau comparatif (≥ 10-15 lignes) avec params exacts
3. Variantes testées et **rejetées** (depuis les commits git)
4. Pièges / post-mortems spécifiques au format
5. Diagnostic de notre config par défaut (vs consensus tops, vs top 1-3)
6. **Playbook 60 min jour J** spécifique à ce format si R2 2026 match

Rapport meta (post-mortems transverse) :
1. ≥ 15 teams top-R1 qui ont crashé en R2 (chiffrés, sourcés)
2. Catégorisation par cause racine (5 catégories : code, stratégie, calibration, équipe, compréhension jeu)
3. Patterns récurrents (top 5)
4. Teams qui ont **remonté** grâce à R2 (≥ 5)
5. Pièges spécifiques à Prosperity 4 2026
6. **Checklist pré-submit** (≥ 15 items dérivés des crashes)

### Comment on exploite ces rapports jour J

1. **T-12h à T-0** (veille au soir → matin release) :
   - Lire les 4 rapports en entier
   - Extraire dans un Google Doc live : tableau **params exacts** par format (hardcoded mean, entry_z, exit_z, target_position, std_window) + **checklist pré-submit** du rapport meta

2. **T+0 à T+30** (release + analyse) :
   - `analyze_r2.py` identifie le format (pair / cross-venue / basket / autre)
   - Ouvrir **le rapport qui match** + **le rapport meta** en parallèle

3. **T+30 à T+90** (activation template) :
   - Le rapport qui match fournit les **params de départ exacts** (pas de fourchette flou)
   - Le rapport meta fournit la **checklist de pièges à vérifier** dans le code

4. **T+90 à T+180** (calibration + submit) :
   - Méthodologie 8-étapes standard, avec grid search dans les ranges suggérés par le rapport spécifique

### Si R2 2026 est un format **inattendu** (pas pair/cross-venue/basket)

Les rapports restent utiles :
- Le rapport meta couvre toutes les éditions, dont les checklists pré-submit
- Les primitives `r2_primitives.py` couvrent les building blocks (z-score hardcodé,
  swmid, safe_order, multi_leg) qui s'appliquent à la plupart des formats
- Les patterns « rolling mean qui étouffe le signal », « multi-leg overshoot »,
  « features exogènes distractrices » sont **universels**, pas spécifiques au format

Dans ce cas : tomber sur du market making étendu ou un format nouveau. Adapter
un des 3 templates ou écrire une 4e stratégie en suivant la structure de
`trader_r2_template.py`.

---

## Fin

**Principe directeur** : la préparation, c'est 80% du résultat en R2. On a fait
notre part (templates + primitives + backtester + 4 rapports Gemini + playbook).
Demain, on exécute proprement.
