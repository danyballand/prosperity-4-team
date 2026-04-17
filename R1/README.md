# Round 1 — récapitulatif complet

**Statut** : Round 1 terminé. Le code soumis ici continue à scorer sur les 5 rounds,
donc ne jamais le casser. Ce dossier contient tout ce qui a été fait pour R1 :
le champion, les variantes testées (gagnantes et perdantes), le backtester
calibré, et l'historique des stratégies rejetées.

---

## 1. Résultats live R1

| Submit | PnL live | Osmium | Pepper | Delta vs champion |
|---|---:|---:|---:|---:|
| **v31 (champion)** | **+12,159.00** | +4,716.00 | +7,443.00 | baseline |
| v32 (submission 209060) | +12,157.69 | +4,714.69 | +7,443.00 | -1.31 (noise) |

**Top leaderboard** : ~+15,000 XIREC. Gap : ~+3,000 (~25%).

**Verdict** : v31 et v32 sont essentiellement équivalents en live. Le gain +118 XIREC
du backtest 3j de v32 (OFI correction sur Osm) était concentré sur day -2 (+96) et
day -1 (+22), day 0 = 0. Le day 0 étant le meilleur proxy du live, le backtest
avait correctement prédit +0 live. **Confirmé** : -1.31 XIREC vs prédiction 0.

---

## 2. Produits R1

### ASH_COATED_OSMIUM
- **Nature** : mean-reverting autour de 10,000
- **Position limit** : 80
- **std mids** : ~4.29 (très stable)
- **spread moyen** : ~16 ticks
- **depth moyen** : ~18 units/level

### INTARIAN_PEPPER_ROOT
- **Nature** : trending +~1000/jour (+52% de la range)
- **Position limit** : 80
- **std mids** : ~817 (volatile)
- **spread moyen** : ~12 ticks
- **depth moyen** : ~15 units/level

---

## 3. Architecture gagnante (v31)

Le champion combine 7 techniques dans `trader.py` (800 lignes) :

### Osmium
| Technique | Détail |
|---|---|
| **Kalman FV** | Filtre d'état pour estimer FV adaptatif (mais désactivé : fixed_fv=10000 plus stable) |
| **Triple edge MAKE** | Pose 3 niveaux de quotes à edge=97 (55% au meilleur, 30% à -1, 15% à -2) |
| **Pennying** | Si possible, améliorer d'1 tick dans le spread tout en restant à min_edge |
| **Inventory clearing** | Si \|pos\| > 20% limit, clear agressif via TAKE |
| **Inventory-aware take** | Skew des seuils TAKE selon position actuelle |

### Pepper
| Technique | Détail |
|---|---|
| **Bootstrap long** | Dès le tick 0, viser +80 en achetant sous `anchor + 9` |
| **Target bias decay** | Position cible décroît de 30 → 0 linéairement sur le jour |
| **Hold until 97%** | On garde la position long-biased jusqu'à 97% du jour |
| **Trend guard** | Si momentum short_ma et long_ma négatifs, cut le bias |
| **ID markout scoring** | (shadow mode) détecte les bots informés par their markout |

### Paramètres critiques (cliffs)
- `make_edge Osm = 97` (testé : 95→+85, 100→-1197 — cliff étroit)
- `bootstrap_cap_offset = 9` (au-dessus de l'anchor = achat aggressive)
- `max_bias = 30`, `hold_bias_until = 0.97`
- `clearing_threshold = 0.20 * limit`

---

## 4. Backtester — pourquoi c'est critique

Sans backtester fiable, aucune décision ne peut être validée. **3 versions ont été
nécessaires pour arriver à un backtester utilisable**. Les 2 premières sont dans
`rejected/` pour référence historique.

### Les 4 bugs critiques corrigés (v3)

| Bug | Symptôme | Fix |
|---|---|---|
| **B1 — Fuite causale** | Pepper backtest = 105% du live (impossible) | Les `market_trades[T]` sont signal du tick T. Les fills passifs de nos orders postés à T matchent les `market_trades[T+1]` (causalité stricte) |
| **B2 — Book pas décrémenté** | Multi-ordres sur même niveau consomment chacun 10 units → overfill | Mutation du `depth.buy_orders` / `depth.sell_orders` après chaque fill |
| **B3 — Cutoff off-by-one** | `ts > 100_000` inclut ts=100,000 → 1001 snapshots au lieu de 1000 | Changé en `ts >= 100_000` |
| **B4 — Sweep cascade manquant** | Si on pennyise à 10009 et trade CSV à 10010, on n'est pas fillé | Cascade : tout ordre nôtre à prix ≥ tp (côté bid) ou ≤ tp (côté ask) est sweeped first |

### Fidélité mesurée (calibration post-fix)

| Produit | Backtest day 0 | Live day 0 | Fidélité |
|---|---:|---:|---:|
| **Pepper** | +7,410 | +7,443 | **99.6%** ✓ |
| **Osmium** | +1,931 | +4,716 | 41% (plafond structurel) |

### Pourquoi Osmium plafonne à 41%

Le CSV `trades_round_1_day_*.csv` ne contient que les trades **bot-to-bot**
visibles (~5% du vrai flow). Le reste du PnL Osm vient du flow invisible
(fills contre des market orders non enregistrés dans le CSV). **Conséquence** :

- Pepper backtest → tu peux faire confiance en absolu (+500 backtest ≈ +500 live)
- Osmium backtest → comparaison relative entre variantes OK, mais jamais extrapolation en absolu
- **Day 0 backtest = meilleur proxy du live** (confirmé par v32 : backtest d0=0 → live d0=0)

### Usage

```bash
cd R1/
python3 local_backtest_v3.py
# Doit donner : GRAND TOTAL: +27653.0
```

Si le résultat diffère → environnement cassé, debugger avant toute action.

---

## 5. Stratégies testées sur v31 (retest_with_v3.py)

J'ai testé **18+ variantes paramétriques** sur v31, toutes ont perdu ou étaient
équivalentes. Liste exhaustive dans `retest_with_v3.py`. Récapitulatif :

| Variante | Delta vs v31 | Verdict |
|---|---:|---|
| adaptive_fixed_fv Osm | < 0 | Rejeté (désactivé) |
| OBI skew Osm | < 0 | Rejeté |
| Bayesian AR(1) Pep | ~0 | Rejeté (neutre) |
| no microprice Pep | < 0 | Rejeté |
| bootstrap_offset 15/20/30 | < 0 | Rejeté (plus agressif ne gagne pas) |
| max_bias 40/50 | < 0 | Rejeté |
| trend_guard_hold_30 | < 0 | Rejeté |
| friend weights Osm | < 0 | Rejeté |
| shadow_join thin_top | < 0 | Rejeté |
| asymmetric clearing | < 0 | Rejeté |
| take_only_short | < 0 | Rejeté |

**Conclusion** : v31 est un optimum local dans son espace paramétrique.

---

## 6. Add-ons v32 testés (retest_v32_addons.py)

3 add-ons issus de recherche alpha approfondie ont été testés pour v32 :

| Add-on | Backtest 3j | Pep delta | Verdict |
|---|---:|---:|---|
| **OFI Osm** (Cont-Kukanov-Stoikov 2014) α=2.0 hl=50 | **+118** | 0 | **Retenu** (seul gain positif) |
| Toxicity tracker (own markout EWMA) | 0 | 0 | Non testable en backtest (own_trades vide) mais harmless en live |
| Queue-skip (pro-rata queue dilution) | -185 à 0 | 0 | Rejeté (ne déclenche jamais ou hurt) |

**Grid search OFI** (retest_v32_ofi_grid.py) : 42 combinaisons alpha × halflife
testées. Plateau stable autour de α ∈ [1.5, 3.0], hl ∈ [30, 100]. Sign-flip
validé (α positif → +118, α négatif → -144). **Signal réel mais marginal**.

**Live delta** : -1.31 XIREC (prédiction = 0, confirmé).

---

## 7. Structure du dossier R1

```
R1/
├── README.md                    # ce fichier
├── trader.py                    # ★ CHAMPION v31 FROZEN (MD5: a45f0d686e53172163e08ef9dad0081c)
├── trader_v32.py                # v32 = v31 + OFI Osm (dernier submit 209060)
├── local_backtest_v3.py         # ★ backtester calibré 99.6% Pep / 41% Osm
├── datamodel.py                 # fourni par IMC
├── retest_with_v3.py            # harness A/B pour variantes paramétriques v31
├── retest_v32_addons.py         # harness pour add-ons OFI/Toxicity/Queue-skip
├── retest_v32_ofi_grid.py       # grid search OFI (alpha × halflife)
├── data/                        # CSV market data R1
│   ├── prices_round_1_day_{-2,-1,0}.csv
│   └── trades_round_1_day_{-2,-1,0}.csv
├── tutorial_data/               # CSV du tutorial (round 0)
└── rejected/                    # stratégies testées et PERDANTES (voir son README)
    ├── README.md
    ├── trader_stoikov.py
    ├── trader_stoikov_v2.py
    ├── trader_pep_bnh.py
    ├── trader_signal_stack.py
    ├── local_backtest.py        # v1 buggé (causal leak)
    ├── local_backtest_v2.py     # v2 buggé (overfill)
    └── retest_with_v2.py
```

---

## 8. Règles d'or R1

1. **`trader.py` est FROZEN.** Ne jamais modifier directement. Pour tester une variante :
   ```bash
   cd R1/
   cp trader.py trader_backup.py
   cp trader_<nouvelle>.py trader.py
   python3 local_backtest_v3.py
   cp trader_backup.py trader.py
   md5 trader.py   # DOIT = a45f0d686e53172163e08ef9dad0081c
   rm trader_backup.py
   ```

2. **Protocole d'audit** obligatoire pour toute variante — voir
   `../docs/PROMPT_BACKTEST_METHODOLOGY.md` (8 étapes : sanity → swap → grid →
   sign-flip → day-by-day → verdict chiffré).

3. **Fidélité** :
   - Pep 99.6% → tu peux faire confiance en absolu
   - Osm 41% → comparaison relative uniquement, day 0 backtest = meilleur proxy live

4. **TraderData limit 49k chars** — trimmer les history buffers. `trader.py` le fait déjà.

5. **Position limit 80 par produit** — jamais dépasser (sinon order rejeté en entier).

---

## 9. Pour soumettre

Le fichier `trader.py` de ce dossier est celui qui doit être uploadé sur la
plateforme IMC. Il contient v31 tel quel.

Si tu veux soumettre v32 à la place :
```bash
cp trader_v32.py trader.py    # swap
# puis upload trader.py
```

Mais attention — après submit, remettre v31 :
```bash
# récupère v31 depuis git
git checkout trader.py
md5 trader.py   # doit redonner a45f0d686e53172163e08ef9dad0081c
```
