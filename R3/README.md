# Round 3 — "Gloves Off" : Options Trading

> **État** : submit-ready — baseline `+33,036 SS` validée en backtest 3 jours.
> **Lead** : Dany. **Date** : 2026-04-24.
> **Dernière mise à jour** : après intégration Wiki officiel + P1 follow-up + P4 + tentative scalping.

---

## 1 · TL;DR pour l'équipe

- **Backtest baseline** : **+33,036 SS** sur 3 jours.
- **Stratégie** : MM passif sur HYD, VE, et VEV ITM (4000-5100). Strikes 5200+ désactivés (adverse selection non neutralisable sans BS pricing complet).
- **Scalping VEV_5400 testé** (Z-score IV surface residual) : -50 SS vs baseline → **désactivé** (flag `ENABLE_VEV_5400_SCALPING = False`). Code laissé en place pour itération future.
- **Manual Bio-Pods** : bids recommandés **b1 = 750, b2 = 840** (E ~ 85 SS/trade).

---

## 2 · Wiki officiel IMC — specs R3 confirmées

| Item | Valeur | Source |
|---|---|---|
| Produits tradables | HYDROGEL_PACK, VELVETFRUIT_EXTRACT, VEV_{4000..6500} (10 strikes) | Wiki |
| **Limits position** | HYD = **200**, VE = **200**, chaque VEV = **300** | Wiki ✅ |
| TTE (historical days) | day 0 = 8j, day 1 = 7j, day 2 = 6j | Wiki ✅ |
| **TTE (live R3)** | **5 jours** au start | Wiki ✅ |
| Day count convention | 250 trading days/an | confirmé Codex P1 Q5 |
| Settlement | cash-settled à expiry (max(S-K, 0)) | Wiki |
| Manual challenge | Ornamental Bio-Pods (voir §6) | Wiki |

**Correction critique appliquée** : on avait HYD = 80 (dette R1/R2) et VEV limits variables 50-200. Fix au wiki → **+9,107 SS** sur la baseline sans rien changer d'autre.

---

## 3 · Les 12 produits — stratégie finale

| Symbol | Type | Prix obs | Limit | PnL 3j | Stratégie |
|---|---|---:|---:|---:|---|
| `HYDROGEL_PACK` | Stable | ~10,000 | 200 | +8,778 | MM passif (fixed_fv=10000, triple_edge) |
| `VELVETFRUIT_EXTRACT` | Underlying | 5247→5295 | 200 | +7,845 | MM wall_mid adaptatif + microprice |
| `VEV_4000` | Deep ITM | ~1250 | 300 | +5,247 | MM passif (δ≈1, comporte comme VE) |
| `VEV_4500` | Deep ITM | ~750 | 300 | +689 | MM passif |
| `VEV_5000` | ITM | ~260 | 300 | +661 | MM passif |
| `VEV_5100` | Near ITM | ~170 | 300 | +709 | MM passif |
| `VEV_5200` → 6500 | ATM/OTM | | 0* | 0 | **Désactivés** (adverse selection -5k à -14k en MM simple) |
| **TOTAL** | | | | **+33,036** | |

> *Limit forcée à 0 dans `PRODUCT_PARAMS` pour désactiver le MM. Le flag `ENABLE_VEV_5400_SCALPING` peut réactiver un scalping dédié sur 5400 (actuellement off — voir §5).

---

## 4 · Résultats Codex — synthèse par prompt

| Prompt | Question | Verdict | Impact |
|---|---|---|---|
| **P1** | Surface IV + mispricings | VEV_5400 IV cheap (-1.06%), VEV_5300 IV rich (+0.82%) | identifie edge théorique |
| **P1 follow-up** | Stabilité rolling + AR(1) résidu | AR(1) = 0.948, half-life 12.9 ts → Z-score tradeable | motive plan B scalping |
| **P2** | Delta empirique vs BS | δ_emp ≈ 70% × δ_BS sur tous strikes. Lead/lag = 0 | pas d'exploit delta hedge |
| **P3** | Microstructure (trader IDs, OBI) | VEV 5300-6000 flow 100% à l'ask (sell-heavy). **Pas d'exploit SHORT** | invalide la jambe SHORT 5300 |
| **P4** | Spreads / stat arb | **Aucun arb executable**. Butterflies 0 violations. Synthetic VE < 1 tick | pas d'alpha |

**Implication critique P3 sur P1** : on ne peut PAS shorter 5300 (pas de buyers). Le "pair trade" 5300/5400 du plan original est mort → **single-leg LONG 5400 uniquement** → scalping Z-score (plan B).

Détails : `research/SYNTHESE_P1.md`, `research/SYNTHESE_P2_P3.md` (inclut updates P1 follow-up + P4), `codex_p{1,2,3,4}_results/`, `codex_p1_followup_results/`.

---

## 5 · Plan B — Scalping VEV_5400 (tenté, échoué, désactivé)

### Idée

Le résidu IV (VEV_5400_market - surface_fit) a AR(1) = 0.948, std ≈ 0.003. Quand Z = (residual - mean) / std < -2, le marché est "anormalement cheap" → LONG. Exit quand Z > 0 (retour à la normale).

### Implémentation

Modules standalone créés :
- `bs_pricing.py` : Black-Scholes pricing (call, IV Brent bisection, delta, vega, theta). Self-tests OK.
- `iv_surface.py` : fit quadratique y = a·x² + b·x + c en log-moneyness via Gauss-Jordan 3x3 + `IVSurfaceTracker` EMA (alpha=0.02, half-life ~34 ticks) avec dump/load pour JSON persistence.
- Hook dans `trader_r3.py` : `_scalp_vev_5400()` appelée chaque tick si flag activé.

### Résultat backtest

**-50 SS** vs baseline (A+B = 32,986 vs A = 33,036).

### Post-mortem (via `debug_scalp.py`)

- Z < -2 fire **82 fois / 30,000 ticks** (0.27%) → entrées trop rares.
- Z > 0 fire **11,651 fois** → exit trop permissif, position liquidée constamment.
- Market flow 100% à l'ask → impossible d'exit en passif (l'ask qu'on poserait jamais hit). L'exit par hit-bid paye le spread full → **chaque round-trip perd 1-2 ticks**.
- Résidu moyen **systématiquement négatif** (mean = -0.008) → le "Z = 0" n'est pas l'équilibre, il y a un biais structurel dans la surface fit (VEV_5400 plus cheap que le modèle, en permanence).

### État actuel

Flag `ENABLE_VEV_5400_SCALPING = False` dans `trader_r3.py` ligne 27. Code laissé en place, modules intacts. Tu peux réactiver après avoir :
1. recalibré le Z de sortie (seuil > 0 ne marche pas, essayer Z > +1 ou basé sur résidu absolu)
2. trouvé un moyen d'exit passif (quote ask aggressive ? mais flow 0% at-bid)
3. ou simplement tenir jusqu'à expiry (mais expose au spot move)

---

## 6 · Manual Challenge — Ornamental Bio-Pods

### Règles (Wiki)

- Reserves counterparties uniform dans **{670, 675, ..., 920}** (51 valeurs, step 5).
- Tu soumets **deux bids** `b1 < b2`.
- Logique :
  - Si `b1 ≥ reserve` → trade at `b1`.
  - Sinon si `b2 ≥ reserve` :
    - Si `b2 ≥ avg_b2_all_players` → trade at `b2` (full).
    - Sinon → trade at `b2` avec pénalité `((920 - avg_b2) / (920 - b2))^3` sur le PnL.
  - Sinon pas de trade.
- Revente implicite à 920 (confirmé par la formule de pénalité).

### Résultat (script `manual_biopods.py`)

**Recommandation : b1 = 750, b2 = 840**, E[profit/trade] ~ **85 SS**.

**Justification** :
- Le Nash équilibre pur donne (750, 835) avec E = 85.00. Mais il suppose que tous les joueurs convergent pile à avg_b2 = 835.
- (750, 840) sacrifie 0.1 SS/trade dans le scénario Nash mais **résiste bien mieux** si la communauté drift un peu plus haut (ce qui est typique sur ces challenges Prosperity où la prudence pousse avg_b2 vers 840-845).

| (b1, b2) | avg=800 | avg=820 | avg=840 | avg=860 |
|----------|---------|---------|---------|---------|
| (750, 835) | 85.00 | 85.00 | 80.29 | 66.63 |
| **(750, 840)** | 84.90 | 84.90 | **84.90** | 68.58 |

**Décomposition de l'EV** :
- b1 = 750 capte **17 reserves** sur 51 (670..750), profit 170/trade pour ces cas
- b2 = 840 capte **18 reserves** de plus (755..840), profit ~80/trade en équilibre
- Reste 16 reserves (845..920) → 0 trade

---

## 7 · Méthodologie & garde-fous

On applique la **méthodologie 8 étapes** éprouvée R1 + R2 :

1. Copier la donnée localement (pas d'accès direct au live)
2. Backtester exhaustivement sur les 3 jours fournis
3. Auditer PnL **par produit** (jamais juger sur le total global)
4. Isoler les sources d'alpha et de perte
5. Tester une hypothèse à la fois
6. Versionner chaque variant (`_v1`, `_v2`, ...)
7. Confirmer la robustesse (backtest 3 jours + variance)
8. **Ne JAMAIS submit sans audit complet**

> Règle d'or : jamais éditer `trader.py` direct. Toujours créer `trader_<variant>.py` et comparer.

---

## 8 · Structure du dossier

```
R3/
├── README.md                       ← ce fichier
├── trader_r3.py                    ← trader principal (baseline +33,036, scalp OFF)
├── local_backtest_r3.py            ← backtester 12 produits, 3 jours
├── datamodel.py                    ← copie datamodel IMC
│
├── bs_pricing.py                   ← Black-Scholes standalone (call, IV, delta, vega)
├── iv_surface.py                   ← fit quadratique IV + IVSurfaceTracker Z-score
├── debug_scalp.py                  ← instrumentation scalping (fréquence triggers, distribs)
├── test_vev_reenable.py            ← test réactivation VEV 5200+ sans BS (tous fail)
├── tune_hyd_ve.py                  ← grid search HYD/VE make_edge (flat)
├── manual_biopods.py               ← optim bids Bio-Pods (recommande 750/840)
│
├── data/
│   ├── prices_round_3_day_{0,1,2}.csv
│   └── trades_round_3_day_{0,1,2}.csv
├── prompts/                        ← les 4 prompts Codex + mega ChatGPT
├── codex_p1_results/               ← P1 surface IV
├── codex_p1_followup_results/      ← P1 follow-up (rolling, AR(1), timing)
├── codex_p2_results/               ← P2 delta & hedge
├── codex_p3_results/               ← P3 microstructure
├── codex_p4_results/               ← P4 spreads / arb
└── research/
    ├── SYNTHESE_P1.md
    └── SYNTHESE_P2_P3.md           ← inclut updates P1 follow-up + P4
```

---

## 9 · Historique équipe LYON

| Round | Rang | PnL | Notes |
|---|---|---:|---|
| R1 | #366 | +12,157 | Osmium MM v31 (triple_edge, Kalman), Pepper Kalman trend-guard |
| R2 | similaire | +10,577 | v4_fixed_v2 : Osmium side channel + Pepper snap-back + bid MAF=500 |
| R3 | TBD | **+33,036 backtest** | MM HYD+VE+VEV ITM, VEV ATM/OTM off. Manual Bio-Pods (750,840). |

---

## 10 · Références

- Repo : [github.com/danyballand/prosperity-4-team](https://github.com/danyballand/prosperity-4-team)
- Docs stratégiques R2 : `../docs/` (4 Gemini Deep Research PDFs)
- Postmortem R2 : `../R2/POSTMORTEM_R2.md`

---

**Si tu viens de rejoindre le projet** : lis ce README → `research/SYNTHESE_P1.md` → `research/SYNTHESE_P2_P3.md`. Dans cet ordre tu auras tout le contexte.
