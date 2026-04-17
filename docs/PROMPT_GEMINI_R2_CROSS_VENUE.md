# Gemini Deep Research — IMC Prosperity Round 2 : CROSS-VENUE ARBITRAGE (précédent P2 2024)

## Rôle et niveau d'exigence

Tu es un quant cross-venue / FX-style arbitrage senior + research analyst.
Mission de **compétitive intelligence exhaustive** sur le format **cross-venue
arbitrage** qui est apparu en Round 2 de Prosperity 2 (2024) avec **ORCHIDS**
(trading local vs South Archipelago via `conversions`, avec tariffs + features
exogènes sunlight/humidity), et qui peut réapparaître sous une autre forme en
Prosperity 4 R2 (avril 2026).

Je veux que tu explores **au minimum 10 repos GitHub** de participants
Prosperity 2 (pas juste les top 3), que tu **lises le code Python réel** du
Round 2 (`trader.py` R2 spécifiquement), et que tu extraies la **mécanique exacte**
des conversions + tariffs, les **paramètres** des top stratégies, et le **piège
majeur** des features exogènes distractrices.

## Ma situation précise

### La compétition en cours
- **Édition actuelle** : IMC Prosperity 4 (avril 2026)
- **R1 soumis** : +12,157.69 XIREC, gap ~3k sous top
- **R2 imminent** : format inconnu
- **Mon hypothèse cible pour ce rapport** : si R2 2026 est un cross-venue (format P2 2024), j'ai besoin des mécaniques de conversion + params exacts + identification du piège « features exogènes qui ne servent à rien »

### Ce que j'ai déjà préparé (à ne PAS redupliquer)

Dans `R2/trader_r2_template.py` j'ai une config `CROSS_VENUE_CONFIG` :
```python
CROSS_VENUE_CONFIG = {
    'enabled': False,
    'product': 'ORCHIDS',
    'use_conversions': True,
    'entry_threshold_pnl': 2.0,   # seuil en XIREC par unit après tariffs
    'position_cap': 50,
    'ignore_exogenous_features': True,  # ⚠ sunlight/humidity = distractions
    ...
}
```

Dans le handoff (`R2/README.md`), j'ai déjà noté : « P2 R2 = ORCHIDS cross-venue,
attention aux features exogènes distractrices comme sunlight/humidity ».

Ce que je n'ai PAS et que je veux de toi : la **mécanique précise** de `conversions`
(quand appeler, avec quel signe, limites per-tick), le **calcul exact du PnL** après
tariffs (transport + import/export + shippin g fees), les **paramètres de seuil**
utilisés par les tops, et la **preuve chiffrée** que sunlight/humidity étaient du
bruit (pas juste une opinion).

## Mission pour toi

### Partie 1 — Mécanique ORCHIDS P2 2024

Reconstruis la **mécanique complète** du Round 2 P2 2024 depuis les sources
primaires (IMC wiki archive, Discord, writeups, code source) :

1. **Règles du jeu** :
   - Position limit ORCHIDS : combien ?
   - `conversions` : quelle est la limite par tick ? signe + vs - ?
   - Tariffs : quelle formule exacte ? (transport fee flat ? import tax pourcentage ? storage cost si |pos|>0 ?)
   - Prix South Archipelago : dans quel champ du `Observation` object ?
   - Fréquence de mise à jour des prix South vs local ?

2. **Features exogènes** :
   - Sunlight : dans quel champ ? fréquence update ? range observé ?
   - Humidity : idem
   - **Étaient-elles corrélées au prix ORCHIDS** (r² > 0.3) ou était-ce du bruit déclaré par IMC comme « distracting feature » post-compétition ?

3. **PnL breakdown typique** :
   - Combien de XIREC les top ont tiré de ORCHIDS R2 ?
   - Combien du pure cross-venue (buy low venue A, sell high venue B) vs du market making local ?

### Partie 2 — Exploration GitHub exhaustive (min 10 repos P2 2024)

Pour chaque repo R2 ORCHIDS :

1. **Identification** : team, rang, score R2, lien `trader.py` R2
2. **Approche** : pure arbitrage cross-venue ? MM local + arb ? arb seulement sur gros deltas ?
3. **Seuil d'entrée** : valeur exacte du profit-per-unit après tariffs requis pour trigger (`entry_threshold_pnl`)
4. **Gestion position** : max position tenu, rebalance rule, cycle time
5. **Utilisation de sunlight/humidity** :
   - Ignorée complètement (consensus attendu) ?
   - Utilisée comme feature prédictive (et ça a marché ? ou c'était du overfit ?)
6. **Conversions** : timing d'appel, signe, quantity
7. **Extrait de code** du cœur de la logique (10-20 lignes)

### Partie 3 — Tableau comparatif (min 10 lignes)

Colonnes :
- Team / rang P2
- Score R2 ORCHIDS
- Approche (pure arb / MM+arb / signal-based)
- entry_threshold profit per unit
- position_cap utilisé
- Conversions timing (every tick / triggered / batch)
- Sunlight/humidity : used / ignored
- Notable tricks

### Partie 4 — Piège confirmé des features exogènes

Cherche les **preuves chiffrées** que sunlight/humidity étaient du bruit :
- Teams qui ont essayé de les modéliser et combien elles ont perdu par rapport au baseline
- Post-mortems publics (blogs, YouTube) qui expliquent le piège
- Analyse statistique : r² sunlight vs prix orchids sur les 3 jours CSV ?

Si au contraire il existe un top team qui a prouvé qu'une feature exogène
**était** prédictive, donne-moi le détail exact avec preuve quantitative.

### Partie 5 — Variantes testées et REJETÉES

Depuis les historiques git des tops :
- Régressions multi-features (sunlight + humidity + volume + …) → combien de XIREC perdus
- Entry threshold trop agressif / trop conservateur
- Bugs de conversions (signe inversé, quantité > limite → tout rejeté)
- Sur-réaction aux features exogènes bruitées

### Partie 6 — Post-mortems et erreurs fatales

- Teams top-R1 qui se sont cassés R2 cross-venue : pourquoi ?
- **CarterT27 P3 R2** (overshoot position limit → rejet total du tick) — bien que P3, vérifier si patterns similaires chez P2 tops
- Erreurs de signe sur conversions
- Confusion venue A vs venue B

### Partie 7 — Diagnostic de MA config par défaut

Compare explicitement mon `CROSS_VENUE_CONFIG` aux tops P2 2024 :
- `entry_threshold_pnl = 2.0` : trop haut, trop bas, bien calibré ?
- `position_cap = 50` : trop conservateur ?
- `ignore_exogenous_features = True` : consensus tops ou décision personnelle ?

### Partie 8 — Playbook 60 min jour J

Si R2 2026 s'avère cross-venue :
1. 3 signaux dans le CSV qui confirment c'est un cross-venue
2. Où chercher les tariffs dans le `Observation` object / manuel IMC
3. Formule exacte du PnL net à coder dès les 15 premières minutes
4. Les 2 pièges à éviter (signe conversions, features exogènes)
5. Params de départ exacts (pas de fourchette)

## Format livrable

```
# Compétitive Intelligence — Cross-Venue Arb R2 (P2 2024 → P4 2026)

## 1. Mécanique ORCHIDS P2 2024 (règles du jeu)
## 2. Repos P2 2024 explorés (min 10)
## 3. Tableau comparatif (min 10 lignes)
## 4. Preuve chiffrée : features exogènes = bruit ?
## 5. Variantes testées et rejetées
## 6. Post-mortems
## 7. Diagnostic de ma config
## 8. Playbook jour J (60 min)
## 9. Sources complètes
```

## Points d'attention

- **Pas de confusion P2 R2 vs P2 R3**. P2 R2 = ORCHIDS cross-venue. P2 R3 =
  GIFT_BASKET (4C+6S+1R) basket arb. **Reste sur R2.**

- **Pas de confusion P2 R2 vs P3 R2**. P3 R2 = PICNIC_BASKET. Pour ORCHIDS
  spécifiquement.

- **Mécanique de `conversions`** : c'est le cœur du sujet. Si tu n'arrives pas
  à la reconstruire depuis les sources, dis-le clairement — je n'ai pas besoin
  d'une description approximative, j'ai besoin de l'API exacte.

- **Code réel > README**. Les tops peuvent avoir simplifié en surface.

- **Citation précise** : lien fichier + ligne pour chaque technique.

## Repos P2 2024 à démarrer

- https://github.com/ericcccsliu/imc-prosperity-2 (P2 #2, Linear Utility)
- https://github.com/jmerle/imc-prosperity-2 (P2 #9, code clean)
- https://github.com/pe049395/IMC-Prosperity-2024 (P2 #13)
- Cherche "imc-prosperity-2" + "ORCHIDS" sur GitHub

---

**Priorité : reconstruction exacte de la mécanique ORCHIDS R2 (conversions + tariffs).**
Sans ça, le reste n'a pas de valeur.
