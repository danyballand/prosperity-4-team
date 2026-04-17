# Gemini Deep Research — IMC Prosperity Round 2 : META POST-MORTEMS (toutes éditions)

## Rôle et niveau d'exigence

Tu es un quant risk + research analyst senior, spécialisé en **analyse d'échecs**.
Mission de **compétitive intelligence sur les erreurs fatales** commises au
Round 2 par des teams qui étaient top-R1, toutes éditions confondues
(Prosperity 1 2023, Prosperity 2 2024, Prosperity 3 2025).

L'objectif n'est **pas** de trouver la meilleure stratégie (les 3 autres
rapports spécifiques couvrent pair / cross-venue / basket). L'objectif est
de construire une **checklist d'erreurs à ne pas commettre** pour mon R2 à
Prosperity 4 (avril 2026), basée sur ce qui a réellement explosé en live
chez les autres — avec chiffres, dates, et commits si possible.

## Ma situation précise

### La compétition en cours
- **Édition actuelle** : IMC Prosperity 4 (avril 2026)
- **R1 soumis** : +12,157.69 XIREC, gap ~3k sous top ~15k
- **R2 imminent**
- **Mon risque principal** : casser R1 en ajoutant du code R2 (multi-product orchestrateur), ou faire une erreur fatale qui transforme un +15k potentiel en -50k

### Ce que j'ai déjà identifié (à ENRICHIR, pas redupliquer)

Dans le `HANDOFF.md` section 9, j'ai déjà noté :
1. **Position limit overshoot = rejet total** (CarterT27 P3 R2)
2. **Rolling mean sur spread persistant** → z-score étouffé → 0 trade
3. **TraderData 49k chars max** → trimmer buffers
4. **Over-fit 3 jours CSV** (Matius Chong P3 R2 OK / R5 catastrophe)
5. **TAKE-only** → friction mange le signal
6. **Features exogènes séduisantes** (P2 sunlight/humidity)
7. **Équipe** : dispute 10 min avant deadline, code change 30 min avant submit, double travail

Ce que je veux de toi : **enrichir** avec ≥ 20 nouvelles erreurs documentées,
toutes **chiffrées** (XIREC perdus, rang avant/après R2), avec **source** (blog,
Reddit, Discord, YouTube, commit git), catégorisées par **cause racine**.

## Mission pour toi

### Partie 1 — Enquête sur les « crashs R2 » toutes éditions

Pour chaque édition (P1 2023, P2 2024, P3 2025), trouve :

- **≥ 5 teams qui étaient top 20 R1 et ont perdu significativement en R2**
- Pour chacune :
  - Nom / rang R1 / rang R2 / delta rang
  - Score R1 / score R2 / delta XIREC
  - Cause racine identifiée (bug code ? mauvaise stratégie ? overfit ? features exogènes ?)
  - Source (commit SHA, blog post, Discord msg, YouTube)
  - Citation directe (quote) si possible

### Partie 2 — Catégorisation par cause racine

Range les échecs par catégorie :

#### A. Erreurs d'exécution / code
- Position limit overshoot → rejet total du tick
- Signe inversé (short au lieu de long)
- Lookahead bias (utilisation de data future)
- Division par zéro (spread=0, std=0)
- TraderData > 49k chars → `state.traderData` tronqué → perte de state
- Erreur de parsing `state.position.get(product, 0)` vs `state[product]`
- Timezone / cutoff off-by-one sur ticks

#### B. Erreurs de stratégie
- Rolling mean trop long / trop court
- Over-trading (entry_z trop bas → slippage)
- Under-trading (entry_z trop haut → pas de fill)
- Ne pas exit avant fin du round (position ouverte pénalisée)
- Stop-loss trop serré → stop-out bruiteux
- Pas de cap_gross_orders safety → rejet

#### C. Erreurs de calibration
- Overfit 1 jour sur les 3 jours CSV
- Mean rolling rapide qui drift → perte du signal persistant
- Recalibration entre jours CSV sans réinit de position
- Utilisation de day-3 CSV en train (mais day-3 est le test IMC)

#### D. Erreurs d'équipe / process
- Changement de code < 30 min avant deadline
- Merge conflict non résolu → submit de la mauvaise branche
- Pas de version control → perte de code champion R1
- Double submit (overwrite accidentel)
- Dispute sur qui soumet

#### E. Erreurs de compréhension du jeu
- Suivre des features exogènes distractrices (P2 sunlight/humidity)
- Interpréter P2 R2 comme un basket (c'est cross-venue)
- Interpréter P3 R2 comme un pair (c'est basket)
- Ignorer le fait que R1 continue à scorer en R2 (pas refactor R1)

### Partie 3 — Tableau synthétique (min 25 lignes)

Colonnes :
- Edition (P1/P2/P3)
- Team / rang R1
- Delta rang R1→R2
- XIREC perdus en R2 vs attendu
- Cause racine (catégorie A-E)
- Description courte (1 ligne)
- Source (lien)

### Partie 4 — Patterns récurrents

Après les 25+ cas, identifie les **3-5 patterns qui reviennent le plus**.
Par exemple :
- « 12/25 des crashs ont été causés par position limit overshoot multi-leg »
- « 8/25 des crashs par rolling mean trop réactif »
- etc.

Pour chaque pattern, donne une **règle de mitigation** actionnable.

### Partie 5 — Les teams qui ont **remonté** en R2

Pour équilibrer — l'objectif c'est aussi de gagner du rang, pas juste de ne pas
en perdre. Trouve **≥ 5 teams** qui étaient hors top 50 R1 et qui ont cassé le
top 20 grâce à R2. Qu'ont-elles fait ?
- Stratégie R2 spécifiquement adaptée au format observé
- Changement radical d'approche entre R1 et R2
- Exploitation de mécaniques peu documentées

### Partie 6 — Pièges spécifiques à PROSPERITY 4 2026

Étant donné :
- R1 = Osmium stable + Pepper trending (format classique 1+1)
- Position limit = 80 par produit R1
- Matching = pro-rata uniform
- R2 format = inconnu

Raisonne sur les **scénarios R2 les plus probables** et les **pièges associés** :
1. Si R2 ajoute 2-3 nouveaux produits : gestion multi-product dans un seul `trader.py`
2. Si R2 introduit une nouvelle mécanique (conversions type P2) : où vérifier dans `state`
3. Si R2 change le position limit global (somme des ordres) : vérifier le wording du manuel
4. Si R2 introduit des produits dérivés des R1 : risque de casser la stratégie R1

### Partie 7 — Checklist pré-submit jour J R2

Donne-moi une **checklist à cocher avant submit R2** issue de l'analyse des échecs :
- [ ] Sanity R1 (trader R1 backtest ≈ 27,653 XIREC avec mon v3 backtester)
- [ ] Tests position limit multi-produit (exhaustif pour chaque produit × leg)
- [ ] Sign-flip test sur signaux directionnels
- [ ] TraderData size < 40k chars après 1000 ticks
- [ ] Day-by-day decomposition du backtest (pas de day avec > 70% du gain)
- [ ] … (au moins 15 items, dérivés des 25+ crashes étudiés)

## Format livrable

```
# Meta — Post-mortems R2 toutes éditions IMC Prosperity

## 1. Enquête crashes R2 (≥ 15 teams documentées)
## 2. Catégorisation par cause racine (5 catégories)
## 3. Tableau synthétique (min 25 lignes)
## 4. Patterns récurrents (top 5)
## 5. Teams qui ont remonté en R2 (≥ 5)
## 6. Pièges spécifiques à Prosperity 4 2026
## 7. Checklist pré-submit jour J (≥ 15 items)
## 8. Sources complètes
```

## Points d'attention

- **Chiffres obligatoires pour chaque claim**. Si tu dis « team X a perdu gros »,
  donne le delta XIREC. Sans chiffre, l'anecdote ne vaut rien.

- **Source obligatoire** : lien blog, commit SHA, msg Discord, timestamp YouTube.
  Si c'est folklore non sourçable, le marquer explicitement `[anecdotal, non vérifié]`.

- **Pas de généralité creuse**. « Soyez prudents » ne m'aide pas. « Vérifiez
  que somme des ordres par produit ≤ limit avant return » m'aide.

- **Cite les cas célèbres connus** :
  - CarterT27 P3 R2 (position limit overshoot)
  - Matius Chong P3 (R2 OK / R5 catastrophe, overfit)
  - … et tous les autres que tu trouves

- **Code réel > README**. Certains crashes sont visibles dans les commits
  (ex: fix hotfix 5 min avant deadline qui a été réverté).

## Repos à explorer (non exhaustif)

- https://github.com/CarterT27/imc-prosperity-3 (R2 post-mortem public)
- Tous les repos cités dans les 3 autres prompts
- Reddit r/algotrading, r/quant — chercher « IMC Prosperity round 2 post mortem »
- Discord IMC Prosperity (si archives accessibles)
- Blog Medium / Substack avec tag "imc prosperity"
- YouTube : chercher « IMC Prosperity writeup » + « round 2 »

---

**Objectif final** : que ce rapport soit ma « liste de bombes à désamorcer » avant
le submit R2, pas une liste de bonnes pratiques vagues. Concret, chiffré, sourcé.
