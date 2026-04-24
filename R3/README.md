# Round 3 — Options Trading (VELVETFRUIT)

> **État** : en cours — baseline `+23,929` backtest validé, alpha discovery via Codex en cours.
> **Lead** : Dany. **Deadline** : TBD (24 avril 2026).
> **Dernière mise à jour** : après Codex P1 (IV surface).

---

## 1 · Le format du Round 3 en 3 phrases

R3 change complètement de registre : **au lieu de spot, on trade des options**. L'univers se compose de :
- **1 produit stable** (`HYDROGEL_PACK`) — comportement type Osmium/Kelp des rounds précédents.
- **1 underlying** (`VELVETFRUIT_EXTRACT`, noté **VE**) — actif sous-jacent des options.
- **10 call options européens** (`VEV_4000` à `VEV_6500`) — des calls sur VE avec strikes différents, **même expiration** (TTE ~7 jours à t=0).

L'enjeu : **market-making intelligent sur VE et HYD** + **détection de mispricings sur les options** via la surface IV.

---

## 2 · Les 12 produits, en détail

| Symbol | Type | Prix obs | Spread | Limit | Logique trading |
|---|---|---|---|---|---|
| `HYDROGEL_PACK` | Stable | ~10,000 | 16 | 80 | MM passif classique (fixed_fv=10000, triple_edge) |
| `VELVETFRUIT_EXTRACT` | Underlying | 5247→5295 | 5 | 200 | MM avec wall_mid adaptatif + microprice |
| `VEV_4000` | Call deep ITM (δ≈1) | ~1250 | 2 | 200 | MM simple — comporte comme VE |
| `VEV_4500` | Call deep ITM | ~750 | 2 | 200 | MM simple |
| `VEV_5000` | Call ITM | ~260 | 2 | 100 | MM passif |
| `VEV_5100` | Call near ITM | ~170 | 2 | 100 | MM passif |
| `VEV_5200` | Call ATM | ~90 | 2 | 100 | ⚠️ MM dangereux (adverse selection) |
| `VEV_5300` | Call ATM | ~50 | 2 | 80 | 🔥 **SHORT directionnel** (IV surcotée +0.01) |
| `VEV_5400` | Call OTM | ~24 | 2 | 80 | 🔥 **LONG directionnel** (IV sous-cotée -0.01) |
| `VEV_5500` | Call OTM | ~12 | 2 | 80 | ⚠️ Illiquide, pas d'edge |
| `VEV_6000` | Call deep OTM | ~1 | 1 | 50 | ❌ Intrinsic ~0, ne pas trader |
| `VEV_6500` | Call deep OTM | ~0 | 1 | 50 | ❌ Illiquide |

> ⚠️ Limits **présumées**, à confirmer avec le Wiki IMC Prosperity 4.

### Pourquoi les options compliquent

- **Pricing options** = la valeur dépend de (S, K, T, σ, r), pas d'un simple wall_mid
- **Adverse selection violente** : les options ATM/OTM sont traded par des bots avec pricing précis. Un MM naïf qui quote symétriquement autour du mid **saigne** (-11,000 sur nos 3 jours en v1).
- **Solution** : soit (a) Black-Scholes pricing rigoureux, soit (b) désactiver les strikes dangereux, soit (c) exploiter le mispricing du MM adverse.

---

## 3 · Baseline actuelle (v2)

**Backtest 3 jours : +23,929 seashells**

| Produit | PnL 3j | Stratégie |
|---|---:|---|
| HYDROGEL_PACK | +8,778 | MM passif (make_edge=97 hérité Osmium, fixed_fv=10000) |
| VELVETFRUIT_EXTRACT | +7,845 | MM passif (wall_mid adaptatif, microprice, make_edge=3) |
| VEV_4000 | +5,247 | MM passif (δ≈1, comporte comme VE) |
| VEV_4500 | +689 | MM passif |
| VEV_5000 | +661 | MM passif |
| VEV_5100 | +709 | MM passif |
| VEV_5200 → 6500 | 0 | **Désactivés** (position_limit=0) |
| **TOTAL** | **+23,929** | |

### Évolution v1 → v2
- **v1** (tout actif, fixed_fv=5250 sur VE) : **-11,115** ❌ (VE saigne -15,910)
- **v2** (fix VE wall_mid + désactivation VEVs OTM) : **+23,929** ✅

---

## 4 · Phase actuelle : Alpha Discovery via Codex

Méthodologie : **4 prompts Codex indépendants** (voir `R3/prompts/`) pour couvrir les 4 angles d'analyse :

| # | Prompt | Question | Statut |
|---|---|---|---|
| P1 | `P1_IV_SURFACE.md` | Surface IV + mispricings par strike | ✅ Reçu |
| P2 | `P2_DELTA_HEDGE.md` | Delta empirique + lead/lag | ⏳ À lancer |
| P3 | `P3_MICROSTRUCTURE.md` | Trader IDs + OBI + régimes | ⏳ À lancer |
| P4 | `P4_SPREADS_ARB.md` | Butterfly + co-intégration | ⏳ À lancer |

Un mega-prompt pour ChatGPT Pro Agent Mode existe également : `prompts/AGENT_GPT_MEGA.md` (browsing + Python sandbox + deep reasoning combinés).

---

## 5 · Résultats Codex P1 : Surface IV

Détail complet dans `R3/codex_p1_results/` et synthèse stratégique dans `R3/research/SYNTHESE_P1.md`.

### Findings en un tableau

| Strike | Direction | IV obs | IV surface | Résidu | Half-spread | EV net (ticks) |
|---|---|---:|---:|---:|---:|---:|
| **5400** | 🟢 **LONG** | 20.70% | 21.75% | **-1.06%** | 0.69 | **+1.43** |
| **5300** | 🔴 **SHORT** | 22.09% | 21.27% | **+0.82%** | 1.05 | **+1.32** |
| 5200 | SHORT marginal | 21.85% | 21.31% | +0.54% | 1.44 | +0.12 |
| 5500 | AVOID | 22.46% | 22.73% | -0.28% | 0.57 | -0.29 |
| 4000, 4500, 5000-5100 | AVOID | — | — | — | — | < -1.67 |
| 6000, 6500 | AVOID | — | — | — | — | -0.33, -0.44 |

### Stabilité jour par jour (robustesse)

**VEV_5400 LONG :**
| Day | Résidu | EV/trade | % trades profitables |
|---|---:|---:|---:|
| 0 | -0.86% | +1.26 | 86.2% |
| 1 | -1.10% | +1.53 | **100.0%** |
| 2 | -1.21% | +1.50 | 98.5% |

**VEV_5300 SHORT :**
| Day | Résidu | EV/trade | % trades profitables |
|---|---:|---:|---:|
| 0 | +0.48% | +0.46 | 69.9% |
| 1 | +1.01% | +1.92 | 94.5% |
| 2 | +0.96% | +1.57 | **99.99%** |

**Signal stable et se renforce** sur les 3 jours. Pas un artefact d'un seul jour.

### Interprétation stratégique

Le résidu IV **ne converge PAS** sur les 3 jours (il diverge même légèrement). Cela signifie :
- **Pas de mean-reversion tradable** au sens classique.
- Mais **signature structurelle** du market maker d'IMC : le MM quote 5300 "trop haut" et 5400 "trop bas" systématiquement → **ce pattern persistera en live**.

---

## 6 · Stratégie proposée — Pair Trade 5300/5400

### Principe

Au lieu de trader les 2 strikes séparément, on construit un **pair trade** qui exploite l'anomalie d'adjacence :

```
LONG VEV_5400 (IV cheap) + SHORT VEV_5300 (IV rich)
```

### Exécution : Skewed MM one-sided

- **VEV_5400** : on quote **UNIQUEMENT le bid** (pas d'ask), pennying inside. Build jusqu'à +40 contracts.
- **VEV_5300** : on quote **UNIQUEMENT l'ask** (pas de bid), pennying inside. Build jusqu'à -40 contracts.
- Pas de crossing du spread (coût 0 en half-spread).

### Delta hedge VE

- δ(5400) ≈ **0.21** (OTM, calculé BS avec IV=20.7%, T=7/250)
- δ(5300) ≈ **0.40** (ATM, IV=22.1%)
- **Delta net par pair** = 0.21 - 0.40 = **-0.19**
- Pour 40 pairs : net delta = -7.6 → **LONG 8 VE** pour neutraliser

### EV chiffrée (scenarios pondérés)

| Scenario | Proba | PnL impact |
|---|---|---:|
| IV reverts + expiry worthless | 30% | +3,000 SS |
| IV persists + expiry worthless | 40% | +1,500 SS |
| S > 5300 à expiry (short 5300 hurts) | 20% | -2,000 SS |
| Vol spike | 10% | -500 SS |
| **EV attendue** | | **+1,050 SS** |

Modeste mais positif, bornée des deux côtés.

---

## 7 · Questions ouvertes (avant de coder)

1. **TTE en live** : les 3 jours de backtest couvrent TTE 7j → 4j. Combien de jours reste-t-il en LIVE après notre submit ? Ça change les deltas/vegas.
2. **Position limits officielles** : toutes présumées, à confirmer sur le Wiki IMC.
3. **Règle de settlement** : cash-settled ou exercice automatique ? Si cash-settled, OK. Si exercice automatique, il faut liquider avant expiry.
4. **Bidding/MAF en R3** : existe-t-il encore un système de bid sealed auction comme en R2 ?

---

## 8 · Structure du dossier

```
R3/
├── README.md                      ← ce fichier
├── trader_r3.py                   ← trader principal (v2, baseline)
├── local_backtest_r3.py           ← backtester adapté R3 (12 produits, 3 jours)
├── datamodel.py                   ← copie du datamodel IMC
├── data/
│   ├── prices_round_3_day_{0,1,2}.csv   ← order book (3 × 6.5MB)
│   └── trades_round_3_day_{0,1,2}.csv   ← trades publics (3 × 50KB)
├── prompts/                       ← prompts de recherche alpha
│   ├── P1_IV_SURFACE.md           ← ✅ Reçu Codex
│   ├── P2_DELTA_HEDGE.md          ← ⏳ À lancer
│   ├── P3_MICROSTRUCTURE.md       ← ⏳ À lancer
│   ├── P4_SPREADS_ARB.md          ← ⏳ À lancer
│   └── AGENT_GPT_MEGA.md          ← mega-prompt ChatGPT Pro Agent
├── codex_p1_results/              ← outputs Codex P1
│   ├── summary.txt
│   ├── ev_by_strike.png
│   ├── iv_surface_by_day.png
│   ├── z_scores_by_strike_time.png
│   ├── iv_surface_by_day_summary.csv
│   ├── iv_surface_overall_summary.csv
│   └── iv_surface_fit_diagnostics.csv
└── research/
    └── SYNTHESE_P1.md             ← synthèse stratégique + plan d'intégration
```

---

## 9 · Méthodologie (pour l'équipe et les observateurs externes)

On applique la **méthodologie 8 étapes** éprouvée depuis R1 :

1. **Copier la donnée localement** (pas d'accès direct au live)
2. **Backtester exhaustivement** sur les 3 jours fournis
3. **Auditer PnL par produit** (jamais juger sur le total global)
4. **Isoler les sources d'alpha et de perte** (quel produit gagne, pourquoi)
5. **Tester une hypothèse à la fois** (éviter les patchs cumulés qui cachent l'effet)
6. **Versionner** chaque variant (`_v1`, `_v2`, `_fixed`, `_stacked`...)
7. **Confirmer la robustesse** (au minimum backtest sur les 3 jours + variance simulation)
8. **Ne JAMAIS submit sans audit complet**

> Règle d'or : **jamais éditer `trader.py` directement. Toujours créer `trader_<variant>.py` et comparer.**

---

## 10 · Historique de l'équipe (LYON)

| Round | Rang mondial | PnL | Notes clés |
|---|---|---:|---|
| R1 | #366 | +12,157 | Osmium MM v31 (triple_edge, Kalman), Pepper Kalman trend-guard |
| R2 | similaire | +10,577 | v4_fixed_v2 : Osmium side channel (+1011) + Pepper snap-back passif + bid MAF=500 |
| R3 | TBD | +23,929 (backtest) | Baseline MM + désactivation VEVs OTM. Alpha via Codex en cours. |

---

## 11 · Références

- Repo : [github.com/danyballand/prosperity-4-team](https://github.com/danyballand/prosperity-4-team)
- Docs stratégiques R2 : `../docs/` (4 Gemini Deep Research PDFs)
- Postmortem R2 : `../R2/POSTMORTEM_R2.md`
- Playbook R2 : `../R2/R2_PLAYBOOK.md`

---

**Si tu viens de rejoindre le projet** : lis `R3/README.md` (ce fichier) → `R3/research/SYNTHESE_P1.md` → `R3/prompts/P1_IV_SURFACE.md`. Dans cet ordre tu auras le contexte complet.
