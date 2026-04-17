# IMC Prosperity 4 — équipe Dany

**Bienvenue.** Ce repo contient tout le code + recherche pour IMC Prosperity 4.
Si tu lis ça, c'est que tu viens de rejoindre. Ci-dessous : 5 min de setup et
tu es opérationnel.

---

## État actuel (R1 post-submit)

- **Submit R1 actuel** : v32 (submission id 209060) = **+12,157.69 XIREC** live
  - Osmium +4,714.69 / Pepper +7,443.00
  - v31 baseline (identique en live) = +12,159 XIREC
  - Gap avec le top : environ +3,000 XIREC
- **Champion frozen** : `trader.py` (MD5 `a45f0d686e53172163e08ef9dad0081c`)
- **Backtester** : `local_backtest_v3.py` calibré Pepper 99.6% / Osmium 41% fidélité live

---

## Setup (5 min)

### 1. Clone + test

```bash
git clone <repo-url>
cd prosperity-4
python3 -c "import ast; ast.parse(open('trader.py').read())"   # doit OK
python3 r2_primitives.py                                       # self-test
```

### 2. Si tu veux tester le backtester

**Les CSV R1 ne sont PAS dans le repo** (trop lourds + récupérables sur IMC).
Crée le dossier `ROUND_1/` et mets-y :
- `prices_round_1_day_-2.csv`, `prices_round_1_day_-1.csv`, `prices_round_1_day_0.csv`
- `trades_round_1_day_-2.csv`, `trades_round_1_day_-1.csv`, `trades_round_1_day_0.csv`

(Fichiers téléchargés depuis la plateforme IMC.)

Puis :
```bash
python3 local_backtest_v3.py
# Doit donner exactement : GRAND TOTAL: +27653.0
# Si différent → env pas propre, ne pas continuer
```

### 3. Check MD5 champion

```bash
md5 trader.py
# DOIT donner : a45f0d686e53172163e08ef9dad0081c
# Si différent → trader.py a été modifié, restore depuis git
```

---

## Organisation du repo

```
.
├── README.md              # ce fichier
├── datamodel.py           # fourni par IMC (Order, OrderDepth, TradingState)
├── trader.py              # ★ CHAMPION v31 (FROZEN — ne pas toucher)
├── trader_v32.py          # v32 = v31 + OFI Osm (submit R1 current)
│
├── local_backtest_v3.py   # ★ SEUL backtester fiable
├── retest_with_v3.py      # harness A/B variantes v31
├── retest_v32_addons.py   # harness A/B addons v32
├── retest_v32_ofi_grid.py # grid search OFI
│
├── analyze_r2.py          # ★ 1-click analyse CSV R2 (stats, corr, basket, ADF)
├── r2_primitives.py       # ★ building blocks (SpreadTrader, BasketPricer, HardcodedMeanZ...)
├── trader_r2_template.py  # ★ skeleton plug-and-play 3 templates (PAIR / BASKET / CROSS_VENUE)
│
├── docs/                  # prompts + méthodologie (à LIRE avant de coder)
│   ├── R2_PLAYBOOK.md               ★ decision tree 180-min release day R2
│   ├── PROMPT_OPUS_R2.md            onboarding Opus 4.7 avec learnings R1
│   ├── PROMPT_BACKTEST_METHODOLOGY.md  protocole audit 8 étapes
│   ├── PROMPT_ALPHA_RESEARCH.md     recherche alpha offline
│   └── gemini_deep_research_prompt.md
│
├── rejected/              # stratégies testées et RATÉES (ne pas refaire)
│   ├── trader_stoikov.py         # +84 XIREC (catastrophe)
│   ├── trader_stoikov_v2.py      # -15k vs v31
│   ├── trader_pep_bnh.py         # -4,367
│   ├── trader_signal_stack.py    # -166,874 (worst)
│   ├── local_backtest.py         # v1 buggé (causal leak)
│   ├── local_backtest_v2.py      # v2 buggé (overfill)
│   └── retest_with_v2.py
│
└── archive/               # recherche, versions, dumps IA
    ├── versions/          # trader_v1 → v20 (historique)
    ├── backtests/
    ├── codex_*/           # outputs IA Codex
    └── gemini_*/          # outputs IA Gemini
```

---

## Règles d'or (à LIRE avant tout)

1. **`trader.py` est FROZEN.** Pour tester une variante :
   ```bash
   cp trader.py trader_backup.py
   cp trader_<nouvelle>.py trader.py
   python3 local_backtest_v3.py
   cp trader_backup.py trader.py
   md5 trader.py   # doit = a45f0d686e53172163e08ef9dad0081c
   rm trader_backup.py
   ```

2. **Protocole d'audit OBLIGATOIRE** pour toute variante :
   - Voir `docs/PROMPT_BACKTEST_METHODOLOGY.md`
   - 8 étapes : sanity baseline → swap → sanity OFF → grid → sign-flip → day-by-day → verdict chiffré
   - Pas de submit sans le protocole complet

3. **Fidélité backtester** :
   - Pepper 99.6% → tu peux faire confiance en absolu
   - Osmium 41% → comparaison relative uniquement, jamais extrapoler en absolu
   - Day 0 backtest = meilleur proxy live (confirmé par v32 : backtest d0=0 → live d0=0)

4. **Stratégies DÉJÀ TESTÉES qui PERDENT** (voir `rejected/`) :
   - Stoikov-Avellaneda
   - Pure buy & hold Pep
   - Signal stack TAKE-only
   - make_edge Osm ≠ 97 (95→+85, 100→-1197)
   - 18 autres variantes paramétriques (voir `retest_with_v3.py`)
   - **Ne pas retenter sans raison très forte**

---

## Préparation R2 (aujourd'hui)

### Ouvre **`docs/R2_PLAYBOOK.md`** — c'est le plan détaillé 180-min

Résumé :
1. **T+0 à T+30** : run `analyze_r2.py ROUND_2/` → identifier structure
2. **T+30 à T+90** : activer le template correct dans `trader_r2_template.py`, remplir configs
3. **T+90 à T+150** : backtest + grid search selon méthodologie
4. **T+150 à T+180** : submit

### Les 3 formats probables pour R2

Basé sur l'historique (corrigé après recherche web) :

| Round historique | Format |
|---|---|
| **P1 R2 (2023)** | Pair cointegration (PINA/COCO, ratio 15/8) |
| **P2 R2 (2024)** | Cross-venue arb (ORCHIDS, tariffs) |
| **P3 R2 (2025)** | Basket/ETF (PICNIC_BASKET 6C+3J+1D) |

Les 3 templates sont prêts dans `trader_r2_template.py`, il suffit d'activer le bon et de remplir les paramètres.

---

## Workflow git recommandé

### Branches
```
main                 # code submit-able à tout moment (uniquement mergé après validation)
├── r2-pair          # exploration pair trading
├── r2-basket        # exploration basket
├── r2-cross-venue   # exploration cross-venue arb
└── <feature>/<name> # expérimentations
```

### Règles
- Merge vers `main` **seulement après backtest > baseline** (protocole méthodologie)
- PR reviewée par l'autre avant merge
- **Submit final = depuis `main`** uniquement, décidé à deux
- Pull avant de commit systématique

### Division du travail (proposition)
Voir `docs/R2_PLAYBOOK.md` section "Stratégies team" — 3 options (split produit / phase / approche).

**Ma recommandation** : split par produit (l'un sur R1+infra, l'autre sur recherche signal R2).

---

## Communication live (pendant R2)

- **Discord/Slack** dédié équipe — indispensable en live
- **Toutes les 30 min** : sync vocal 5 min (statut, blockers)
- **Avant submit** : review croisée du code (20 min obligatoire)
- **Qui a le dernier mot ?** → à décider AVANT R2 (voir R2_PLAYBOOK)

---

## Leçons R1 à retenir (pour ne pas les refaire R2+)

1. **Backtester sans fix causal = faux résultats +20-50%** (bug B1 fixé en v3)
2. **Osmium plafonne à 41% fidélité** — CSV trades ne contient que 5% du vrai flow
3. **Signaux day-specific = overfit** — v32 +118 backtest venait de d-2, live delta = 0
4. **make_edge Osm = 97** est sur une cliff (95→+85, 100→-1197) — sweet spot étroit
5. **Toxicity tracker ne déclenche jamais** avec edges 97/3 — no adverse selection (OWNMO +2 à +8)
6. **TraderData limit 49k chars** — toujours trimmer les history buffers
7. **Position limit overshoot = order rejeté en entier**, pas clamp — toujours `min(qty, limit - pos)`

---

## Premier réflexe (après clone)

```bash
# 1. Lis ces 3 docs dans l'ordre (30 min total)
open docs/R2_PLAYBOOK.md
open docs/PROMPT_BACKTEST_METHODOLOGY.md
open docs/PROMPT_OPUS_R2.md

# 2. Check l'environnement
md5 trader.py    # a45f0d686e53172163e08ef9dad0081c
python3 r2_primitives.py   # All primitives functional

# 3. Appel l'autre pour aligner les rôles
```

Bonne chance — on joue R2 ensemble.
