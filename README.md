# IMC Prosperity 4 — équipe Dany

Repo d'équipe pour IMC Prosperity 4 (avril 2026). Organisé en 2 sous-dossiers
séparés par round.

---

## Navigation rapide

| Je veux... | Aller à |
|---|---|
| Comprendre où on en est (résultat R1 live) | `R1/README.md` |
| Revoir les stratégies R1 qui n'ont pas marché | `R1/rejected/README.md` |
| Préparer R2 (démarre aujourd'hui 18 avril 2026) | `R2/README.md` |
| Décision tree du jour J | `R2/R2_PLAYBOOK.md` |
| Protocole d'audit d'une variante | `docs/PROMPT_BACKTEST_METHODOLOGY.md` |
| Onboarding complet pour Opus 4.7 | `docs/PROMPT_OPUS_R2.md` |

---

## État actuel (17 avril 2026)

- **R1 submitted** : v32 (submission 209060) = **+12,157.69 XIREC live**
  - Osmium +4,714.69 / Pepper +7,443.00
  - Équivalent à v31 (−1.31 XIREC delta = noise)
- **Top leaderboard** : ~+15,000 XIREC → gap ~+3,000 (focus R2+)
- **Backtester v3** : calibré Pepper 99.6%, Osmium 41% fidélité live
- **R2** : démarre aujourd'hui. Arsenal prêt dans `R2/`.

---

## Structure du repo

```
.
├── README.md                  # ce fichier (navigation)
│
├── R1/                        # ROUND 1 — tout ce qui a été fait/testé
│   ├── README.md              # résultats live + architecture v31 + backtester
│   ├── trader.py              # ★ CHAMPION v31 (MD5 a45f0d686e53172163e08ef9dad0081c)
│   ├── trader_v32.py          # v32 = v31 + OFI Osm (dernier submit)
│   ├── local_backtest_v3.py   # backtester v3 calibré
│   ├── datamodel.py           # fourni par IMC
│   ├── retest_with_v3.py      # harness A/B variantes v31
│   ├── retest_v32_*.py        # harness add-ons v32 + grid OFI
│   ├── data/                  # CSV market data R1
│   ├── tutorial_data/         # CSV tutorial
│   └── rejected/              # stratégies TESTÉES ET PERDANTES
│       ├── README.md          # explique pourquoi chaque échec
│       ├── trader_stoikov.py
│       ├── trader_stoikov_v2.py
│       ├── trader_pep_bnh.py
│       ├── trader_signal_stack.py
│       ├── local_backtest.py  # v1 buggé
│       └── local_backtest_v2.py
│
├── R2/                        # ROUND 2 — préparation complète
│   ├── README.md              # quoi / pourquoi / comment backtest
│   ├── R2_PLAYBOOK.md         # ★ decision tree 180-min jour J
│   ├── analyze_r2.py          # 1-click analyse CSV (stats, corr, basket)
│   ├── r2_primitives.py       # building blocks (SpreadTrader, BasketPricer...)
│   ├── trader_r2_template.py  # skeleton plug-and-play 3 templates
│   ├── datamodel.py
│   └── data/                  # (vide — à remplir à la release)
│
├── docs/                      # cross-cutting documentation
│   ├── PROMPT_BACKTEST_METHODOLOGY.md  # protocole audit 8 étapes
│   ├── PROMPT_OPUS_R2.md               # onboarding Opus 4.7 + learnings
│   ├── PROMPT_ALPHA_RESEARCH.md        # recherche d'alpha offline
│   └── gemini_deep_research_prompt.md
│
└── archive/                   # historique (v1 → v30+)
    └── versions/
```

---

## Setup rapide (5 min après clone)

```bash
git clone https://github.com/danyballand/prosperity-4-team.git
cd prosperity-4-team

# Lire le plan R2 (15 min max)
cat R2/R2_PLAYBOOK.md

# Tester le backtester R1 (doit donner +27,653)
cd R1
python3 local_backtest_v3.py

# Tester les primitives R2
cd ../R2
python3 r2_primitives.py
python3 analyze_r2.py ../R1/data/   # sanity sur données R1

# Vérifier l'identité du champion
cd ../R1
md5 trader.py
# DOIT donner : a45f0d686e53172163e08ef9dad0081c
```

Si toutes ces commandes donnent le résultat attendu → environnement OK, tu
es prêt.

---

## Règles d'or

1. **`R1/trader.py` est FROZEN** (MD5 `a45f0d686e53172163e08ef9dad0081c`).
   Ne jamais modifier directement. Pour tester une variante, swap/test/restore.

2. **Protocole d'audit obligatoire** pour toute variante avant submit : voir
   `docs/PROMPT_BACKTEST_METHODOLOGY.md`. 8 étapes. Pas de raccourci.

3. **Day 0 backtest = meilleur proxy live** (confirmé par v32 : backtest d0=0 → live d0=0).

4. **Position limit** : toujours clamp `min(qty, limit - pos)`. Sinon rejet total
   de l'ordre par le match engine (leçon CarterT27 P3 R2).

5. **TraderData limit 49k chars** — trim les history buffers en fin de run.

---

## Workflow git

### Branches
```
main                 # submit-able à tout moment
├── r1-<feature>     # si on doit patcher R1
├── r2-analysis      # exploration R2
├── r2-pair          # si structure = pair
├── r2-basket        # si structure = basket
└── r2-cross-venue   # si structure = cross-venue
```

### Règles
- **Merge vers `main`** = seulement après backtest > baseline validé
- **PR review** par le binôme obligatoire avant merge
- **Submit final** = depuis `main` uniquement, décidé à deux
- **Pull avant commit** systématique

---

## Communication live (pendant un round)

- Discord/Slack dédié équipe
- Sync vocal toutes les 30 min (5 min, status + blockers)
- Review croisée du code avant submit (20 min obligatoire)
- **Qui a le dernier mot** sur le submit final → à décider AVANT chaque round

---

## Liens externes (top teams historiques à consulter si bloqué)

- https://github.com/ericcccsliu/imc-prosperity-2 (P2 #2, basket params exacts)
- https://github.com/chrispyroberts/imc-prosperity-3 (P3 #7 global, allocation ingénieuse)
- https://github.com/Sylvain-Topeza/imc-prosperity-3 (P3 top 1%)
- https://github.com/CarterT27/imc-prosperity-3 (P3 #9, post-mortem position limit)
- https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal (P1 #2)
- https://github.com/nicolassinott/IMC_Prosperity (P1, z-score 1.5)
- https://github.com/jmerle/imc-prosperity-2-backtester (backtester officieux)

---

## Contact

En cas de besoin / blocage pendant un round : vocal Discord, pas d'email.
