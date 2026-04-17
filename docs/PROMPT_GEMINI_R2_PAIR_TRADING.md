# Gemini Deep Research — IMC Prosperity Round 2 : PAIR TRADING (précédent P1 2023)

## Rôle et niveau d'exigence

Tu es un quant cointegration / stat-arb senior + research analyst. Mission de
**compétitive intelligence exhaustive** sur le format **pair trading** qui est
apparu en Round 2 de Prosperity 1 (2023) avec **PINA_COLADAS / COCONUTS**, et
qui peut réapparaître sous une autre forme en Prosperity 4 R2 (avril 2026).

Je veux que tu explores **au minimum 10 repos GitHub** de participants
Prosperity 1 (pas juste les 3 stars), que tu **lises le code Python réel** des
traders.py du Round 2 (pas juste les READMEs), et que tu extraies les **paramètres
exacts** + **variantes testées et rejetées** + **pièges confirmés**.

## Ma situation précise

### La compétition en cours
- **Édition actuelle** : IMC Prosperity 4 (avril 2026)
- **R1 soumis** : +12,157.69 XIREC (Osmium stable + Pepper trending), gap ~3k sous top
- **R2 imminent** : format inconnu — je prépare 3 templates plug-and-play (pair / cross-venue / basket)
- **Mon hypothèse cible pour ce rapport** : si R2 2026 est un pair cointégré (format P1 2023), j'ai besoin des params exacts de tous les tops P1 pour calibrer rapidement

### Ce que j'ai déjà préparé (à ne PAS redupliquer)

Dans `R2/r2_primitives.py` j'ai :
- `SpreadTrader(entry_z, exit_z, limit)` : pair trading avec seuils Z
- `HardcodedMeanZ` : Z-score avec mean hardcodé (pas rolling)
- `swmid`, `safe_order`, `net_delta`, `suggest_hedge`

Dans `R2/trader_r2_template.py` j'ai une config `PAIR_CONFIG` par défaut :
```python
PAIR_CONFIG = {
    'enabled': False,
    'leg_a': 'PINA_COLADAS', 'leg_b': 'COCONUTS',
    'ratio_a': 15, 'ratio_b': 8,    # spread = 15*A - 8*B
    'entry_z': 1.5, 'exit_z': 0.5,  # nicolassinott P1
    'mean_hardcoded': None,          # à calibrer
    'std_window': 100,
    ...
}
```

Ce que je n'ai PAS et que je veux de toi : le détail des **variantes** testées
par les autres tops P1, les **params alternatifs** (ratios, seuils Z, fenêtres),
les **mécanismes d'exit** non-standard (time-based, drawdown-based), la gestion
des **position limits multi-legs** (hedge ratio fractionnaire → clamp).

## Mission pour toi

### Partie 1 — Exploration GitHub exhaustive (min 10 repos P1 2023)

Pour chaque repo, fournis :

1. **Identification**
   - Auteur / équipe, rang final annoncé, rang R2 spécifiquement si trouvé
   - Lien GitHub direct vers `trader.py` du Round 2

2. **Spécification du pair**
   - Quels produits ont-ils tradés ? (PINA/COCO seulement, ou d'autres pairs aussi ?)
   - **Ratio utilisé** : comment calculé ? (hedge ratio OLS dynamique ? static 15/8 ? autre ?)
   - Formule spread exacte (extrait 5-15 lignes)

3. **Mean / Std du spread**
   - Mean : **hardcoded** (quelle valeur exacte ?) ou **rolling** (quelle fenêtre ?)
   - Std : window size, EWMA decay, ou fixed
   - Si hardcoded : comment ont-ils calibré cette valeur ? (moyenne 3 jours CSV ? 1 jour ? last ?)

4. **Seuils d'entrée/sortie**
   - `entry_z`, `exit_z` exacts
   - **Seuil de stop** : stop-loss z ? time-based hold max ?
   - Comportement à z extrême (z > 3, z > 5) : reduce position ? ignore ?

5. **Gestion position / hedge**
   - Si ratio = 15/8 mais limit = 20 par produit → comment ils clampent ?
   - Execution : legs **simultanées** (un tick) ou **séquencées** (A d'abord, B le tick suivant) ?
   - Hedge asymétrique (1 leg taker / 1 leg maker) ?

6. **Interaction avec le matching engine**
   - P1 2023 utilisait-il pro-rata ou LOB FIFO ? (crucial si P4 2026 aussi pro-rata)
   - Impact sur le fill rate des pair-legs

7. **Code quality & commits**
   - Lignes de code du module pair
   - Historique commits : tâtonnement (beaucoup de variantes) ou plan d'un coup ?
   - Tests / backtest présents ?

### Partie 2 — Tableau comparatif (markdown)

Colonnes :
- Team / rang P1
- Score R2 (si dispo)
- Ratio (static ou OLS dynamique)
- Mean (hardcoded valeur vs rolling window)
- Std window
- entry_z / exit_z / stop_z
- Execution sync vs séquencée
- Position size max vs limit
- Notable tricks

**Minimum 10 lignes dans ce tableau.**

### Partie 3 — Variantes testées et REJETÉES

C'est la partie qui m'intéresse le plus. Pour chaque top team dont tu trouves
l'historique git, liste les variantes qui ont été commitées puis supprimées :

- Seuils z essayés et abandonnés (pourquoi ?)
- Rolling mean puis abandonné pour hardcoded (ou l'inverse — avec quelle raison)
- Hedge ratio OLS dynamique puis abandonné pour static (ou l'inverse)
- Exit rules complexes (trailing stop, time exit) essayées et abandonnées

Extrait de commits avec messages si possible.

### Partie 4 — Pièges et erreurs confirmés

Cherche dans les **post-mortems** (blogs, Reddit, Discord, YouTube) :
- Teams qui ont **perdu gros sur R2 pair** malgré un bon R1 : pourquoi ?
- Erreurs de position limit (hedge fractionnaire qui overshoot)
- Erreurs de signe (short/long inversé)
- Erreurs de lookahead (utilisation du spread_t pour trader à t+1 mais avec fill_t)
- Régime changes : le pair s'est décointégré mid-round ?

### Partie 5 — Diagnostic de MA config par défaut

Compare explicitement mon `PAIR_CONFIG` ci-dessus aux params des tops.
Pour chaque clé :
- Ma valeur vs consensus tops
- Ma valeur vs top 1-3 spécifiques
- Risque si P4 2026 R2 est un pair avec caractéristiques différentes (mean qui dérive, ratio non-intuitif, etc.)
- Suggestion de range à grid-searcher au jour J

### Partie 6 — Plan d'action concret pour jour J R2

Si R2 2026 s'avère être un pair trading, donne-moi **un playbook 60 min** :
1. Commandes shell à lancer (ajustées à `R2/analyze_r2.py`)
2. Les 3 signals dans le CSV qui confirment que c'est bien un pair (corrélation, ADF p-value, half-life)
3. Les 2 pièges à vérifier immédiatement (ratio non-intuitif, mean qui bouge entre jours CSV)
4. Les params de départ à utiliser (valeurs exactes, pas de range flou)
5. Les 3 checks A/B à faire avant submit

## Format livrable

Rapport structuré avec liens clickables partout.

```
# Compétitive Intelligence — Pair Trading R2 (P1 2023 → P4 2026)

## 1. Repos P1 2023 explorés (min 10)
## 2. Tableau comparatif (min 10 lignes)
## 3. Variantes testées et rejetées
## 4. Post-mortems : ce qui a tué les pair traders
## 5. Diagnostic de ma config
## 6. Playbook jour J (60 min)
## 7. Sources complètes
```

## Points d'attention

- **Pas de confusion avec Prosperity 2/3**. P1 2023 R2 = PINA/COCO. P2 2024 R2 = ORCHIDS (pas un pair). P3 2025 R2 = PICNIC_BASKET (basket). Reste sur P1.

- **Code réel > README**. Les tops ne révèlent pas tout en surface. Lis les `.py` du R2 spécifiquement (pas le R1).

- **Pièges à ne PAS inventer**. Si tu ne trouves pas l'info, dis « non trouvé » plutôt que confabuler un chiffre. Un seuil inventé me coûte 10 min de backtest inutile le jour J.

- **Budget recherche** : prends le temps qu'il faut. Priorité exhaustivité sur rapidité.

- **Référer chaque technique à un fichier + n° de ligne** (ou function name si non numéroté). Je veux pouvoir vérifier.

## Repos P1 2023 à démarrer (pas exhaustif)

- https://github.com/nicolassinott/IMC_Prosperity (z=±1.5 connu)
- https://github.com/ShubhamAnandJain/IMC-Prosperity-2023-Stanford-Cardinal
- Cherche "imc-prosperity-2023" et "imc prosperity round 2" sur GitHub
- Cherche les writeups blog Medium / Substack / Notion publiés post-compétition

---

**Si tu explores 15-20 repos P1 au lieu de 10, c'est mieux.**
