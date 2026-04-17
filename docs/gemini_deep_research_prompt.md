# Gemini Deep Research — Mission exhaustive IMC Prosperity Round 1

## Rôle et niveau d'exigence

Tu es un quant microstructure senior + research analyst, chargé d'une mission
de compétitive intelligence poussée. Je veux une **couverture exhaustive** de
la littérature GitHub/blog/writeup/YouTube/Discord sur la compétition
**IMC Prosperity** (toutes éditions : Prosperity 1 en 2023, Prosperity 2 en
2024, Prosperity 3 en 2025, Prosperity 4 en cours).

Mon objectif n'est pas un résumé superficiel. Je veux que tu **explores au
minimum 30 repos GitHub** de participants (pas juste les 5 stars les plus
visibles), que tu **lises le code Python réel** (pas juste les READMEs), et
que tu en extraies les techniques structurelles les plus puissantes, en
particulier celles qui s'appliquent à mon Round 1 actuel.

## Ma situation précise

### La compétition

- **Édition** : IMC Prosperity 4 (avril 2026)
- **Round 1 en cours** : 2 produits
  - `ASH_COATED_OSMIUM` : stable autour de 10,000 (std = 5.35, range
    observée 9977-10023, spread moyen 16 ticks, spread max 22)
  - `INTARIAN_PEPPER_ROOT` : légèrement trending (+100 ticks/jour live,
    mid final 12,099 depuis 11,998 — beaucoup moins que l'annoncé +1000/jour)
- **Position limit** : 80 par produit
- **Moteur de matching** : uniforme pro-rata (pas LOB queue classique)
- **Nombre de ticks par round live** : ~10,000
- **Règle limite** : si somme des ordres > limit, TOUS rejetés
- **Manuel Round 1** : Flax 30/9 + Mushroom 18/35 = +66,500 XIREC (à part)

### Mon score actuel

**12,159 XIREC** sur le Round 1 algo pur. Breakdown :
- Osmium : 4,716
- Pepper : 7,443
- Position finale live : Osmium -4, Pepper +80

### Architecture de mon code actuel (v31 champion)

Résumé fonctionnel (Python, ~800 lignes) :

```
Pour chaque produit, chaque tick :
1. Calcul fair value (FV)
   - Osmium : FV fixed = 10,000
   - Pepper : Kalman filter (drift=2.5, Q=0.25, R=200) sur microprice/wall_mid
2. Target bias (Pepper seulement) : accumulation +80 graduelle via bootstrap
3. Skew : skew = -(position - target_bias) * 0.04 ou 0.10
4. TAKE phase : accepte les ask < FV - take_width, bid > FV + take_width
   - inventory_aware_take sur Osmium : shift threshold par skew*2.0
5. INVENTORY CLEARING (Osmium) : quand |pos| > 0.2*limit, take actif
   contre la book opposée
6. MAKE phase : post passifs aux prix FV±make_edge (pennying inside)
   - Osmium : make_edge = 97 (pic découvert empiriquement, cliff à 98)
   - Pepper : make_edge = 3
   - Triple_edge : split 55/30/15 sur 3 prix adjacents
   - Pennying : override make_price par min(bb+1, FV-1) / max(ba-1, FV+1)
7. _cap_gross_orders : safety finale, cap somme orders <= limit par côté
```

### Les tops font combien ?

Sources confirmées par précédente recherche :
- **Linear Utility #2 P2 2024** : **34,498 XIREC algo R1** (sur Amethysts
  stable + Starfruit trend, structure identique à la nôtre)
- **chrispyroberts #1 USA P3 2025** : **~44,000 XIREC R1** (Resin + Kelp)
- **Stanford Cardinal #2 P1 2023** : top 20 R1
- **jmerle #9 P2 2024** : 31,733 algo R1

Je suis donc à **25-35% du top**. Gap = 20,000-35,000 XIREC à combler.

### Ce qui NE MARCHE PAS (exclusion list)

J'ai testé avec instrumentation live et simulation counterfactual :

- Overlays prédictifs : Bayesian AR(1), OBI gate, bucket temporal bias,
  cross-product correlation → tous **NO-OP live** (hash-diff logs identique).
- Sweep make_edge tight (1, 2, 3, 5, 8, 12, 20) backtest : monotone jusqu'à
  plateau à edge=20. Mais live ne suit pas (edge=97 est le pic live strict).
- One-sided jackpot dédié : -8 XIREC vs v31 (déjà capturé par make_edge=97).
- Linear Utility AR(1) θ=-0.229 : signe mauvais sur Pepper (best θ_hist=+0.20,
  best θ_live=+0.50, incohérent → overfit).
- Clear tier "post passive à FV+50 quand long" : 0 fill counterfactual
  (spread=16, pas de bid à 10020+).
- Post-at-fair bid+ask à 10000 : direct edge nul (marché ne transige pas
  assez à 10000 exact, seulement 30 trades/jour sur 3 jours CSV).
- Pepper "floor 60 cycle" : -511 XIREC vs HODL.

### Hypothèses actuelles sur le gap

1. **Architecture d'exécution sous-optimale** (pas de pb d'alpha prédictif).
2. **Mauvaise exploitation du pro-rata matching** (uniform matching vs LOB).
3. **Panic take toxique** sur Osmium quand inventaire extrême.
4. **Dual-layer non exploité** : notre make_edge=97 est écrasé par
   pennying (`max(9903, penny_bid)` active seulement 7.85% du temps quand
   book one-sided).
5. **Pepper coma** : dès |pos|>=76 (flatten=0.95), MAKE block skippé,
   on devient pur HODL, on rate tout le spread restant de la journée.
6. **Techniques des tops 2024/2025 non transposées** au contexte spread=16.

## Mission pour toi

### Partie 1 — Exploration exhaustive GitHub (minimum 30 repos)

Pour chaque édition (P1 2023, P2 2024, P3 2025), liste **au minimum 10 repos**
de participants (pas juste les top 5). Pour chaque repo :

1. **Identification** :
   - Nom auteur / équipe, rang final annoncé, lien GitHub direct
   - Rang R1 spécifiquement si mentionné dans README
   - Score R1 absolu si visible

2. **Technique stable product** (Amethysts / Resin / Pearls) :
   - Fair value exacte (hardcoded 10000 ? wall mid ? autre ?)
   - Edge / skew / tailles utilisées
   - Pennying stratégie (conditions, prix)
   - Trois-tier / dual-tier / mono-tier ?
   - Inventory management (clear tier ? soft limits ? skew doubling ?)
   - Extrait de code si possible (5-15 lignes clé)

3. **Technique trend product** (Starfruit / Kelp / Bananas) :
   - Modèle de FV (EMA ? Kalman ? AR(1) ? OU ? LSTM ? filtrage volume ?)
   - Valeur des coefficients/hyper-paramètres
   - Gestion position limit (directionnel full vs cycling ?)
   - Entry timing, bootstrap ?
   - Extrait de code clé

4. **Astuces microstructure** mentionnées (dans README ou commentaires code) :
   - Bugs engine identifiés, seuils magiques, patterns bots
   - Timing windows exploitées
   - Relation au matching uniform pro-rata

5. **Code quality indicators** : lignes de code, complexité, présence de
   tests/backtest, commits historique (tâtonnement vs planifié)

### Partie 2 — Analyse comparative exhaustive

Construis un **tableau comparatif** (markdown table) avec colonnes :
- Team
- Rang / édition
- Score R1 (si dispo)
- Stable FV method
- Stable edge
- Stable clear mechanism
- Trend FV method
- Trend θ/coeff
- Trend cycling vs HODL
- Triple/dual/mono-layer
- Notable tricks

**Au moins 20 lignes dans ce tableau**. C'est le livrable central.

### Partie 3 — Diagnostic de MON code

Compare explicitement **mon v31 ligne par ligne** avec la moyenne des tops.
Pour chaque décision architecturale, dis-moi :
- Qu'est-ce que font 80% des tops (si consensus) ?
- Qu'est-ce que font seuls les tops 1-3 (si spécifique aux meilleurs) ?
- Qu'est-ce qui est unique à Linear Utility / chrispyroberts / Stanford /
  jmerle / Sylvain-Topeza / autres ?
- Où mon v31 est **sous-optimal** et de combien XIREC estimé ?

### Partie 4 — Stratégies ignorées par la communauté

Cherche des techniques **ésotériques** ou peu citées :
- Anciens rounds précédents (P1, P2, P3 rounds 2-5) où la structure
  "stable + trend" revient — ont-ils trouvé des tricks non transposés à R1 ?
- Academic papers cited by top teams (mean-reversion MM, pro-rata queue,
  adverse selection in MM) — résumé des 3 plus cités
- Discord IMC Prosperity — si accessible via archives/searches, quelles
  sont les plaintes/découvertes récurrentes sur R1 ?
- YouTube writeup videos (certains en font) — 3 meilleures à regarder

### Partie 5 — Plan d'action concret pour moi

Pour passer de 12,159 à 25,000+ XIREC, donne-moi **5 patches ordonnés par
ROI estimé**. Pour chaque patch :
- Description 1 phrase
- Source (quel top team l'utilise)
- Impact estimé XIREC (avec fourchette)
- Difficulté d'implémentation (lines of code)
- **Risque d'overfit** (backtest vs live cohérence attendue)
- Pseudo-code Python directement collable dans mon `trade_product()`

Classe ces 5 patches par **ratio ROI/risque** décroissant.

## Format de ton livrable

**Rapport long, structuré, avec liens clickables partout**. Pas de
résumé "exécutif" de 3 paragraphes — je veux du détail.

Structure attendue :
```
# Compétitive Intelligence IMC Prosperity Round 1 — Rapport complet

## 1. Repos explorés (table 30+ lignes : nom, rang, lien, highlights)

## 2. Comparatif stable product techniques (table 20+ lignes)

## 3. Comparatif trend product techniques (table 20+ lignes)

## 4. Diagnostic v31 : où je suis sous-optimal (point par point)

## 5. Techniques ésotériques / papers / Discord insights

## 6. Plan d'action 5 patches (ordonnés par ROI/risque)

## 7. Conclusion : quelle est la probabilité réaliste d'atteindre 20k+ ?

## 8. Sources complètes (bibliographie clickable)
```

## Points d'attention

- **Pas de confusion Prosperity 4 ≠ Prosperity 3**. P4 2026 utilise
  Osmium/Pepper. P3 2025 utilise Resin/Kelp/Squid_Ink. P2 2024 utilise
  Amethysts/Starfruit. P1 2023 utilise Pearls/Bananas. Structure R1 est
  presque identique (1 stable + 1 trend) à chaque édition → transférabilité.

- **Pro-rata matching** : crucial à comprendre. C'est pas du LOB classique
  FIFO. Ton rapport doit clairement distinguer les techniques spécifiques à
  ce matching (ex: pourquoi triple_edge peut diluer le pro-rata L1).

- **Honnêteté** : si tu ne trouves pas un repo ou une info, dis "non trouvé"
  plutôt qu'inventer. La valeur de ton rapport tient à sa fiabilité.

- **Code réel > READMEs** : lis les .py, pas juste les markdowns marketing.
  Les tops ne révèlent pas tout dans leur README.

- **Citation précise** : pour chaque technique, donne le lien vers le fichier
  précis et idéalement le numéro de ligne ou function name.

## Contexte fichier joint (optionnel)

Si je te fournis mon fichier `trader_v31_champion.py` (800 lignes), tu peux
le lire et le référencer directement. Sinon, base-toi sur la description
architecturale ci-dessus.

---

**Budget recherche** : prends le temps qu'il faut. Priorité à l'exhaustivité
sur la rapidité. Si tu explores 50 repos au lieu de 30, c'est mieux.
L'objectif est qu'après ton rapport, je n'aie plus besoin d'aller chercher
ailleurs.
