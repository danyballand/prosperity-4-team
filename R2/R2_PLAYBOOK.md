# R2 PLAYBOOK — Decision tree release day

**Ce document = ton check-list unique le jour du R2.** Tu l'ouvres, tu suis
les étapes dans l'ordre, tu coches. Pas d'improvisation, pas de panique.

---

## T-12h : PRE-RELEASE CHECKS (ce soir)

- [ ] `md5 trader.py` = `a45f0d686e53172163e08ef9dad0081c` (v31 champion, toujours en place)
- [ ] `trader_v32.py` présent (MD5 `8cb7e489fe7bb5b260cb77921c1ae699`)
- [ ] `r2_primitives.py` self-test passe : `python3 r2_primitives.py`
- [ ] `analyze_r2.py` run sur R1 : `python3 analyze_r2.py ROUND_1/` donne un rapport cohérent
- [ ] `local_backtest_v3.py` baseline : `+27,653` exact
- [ ] Backup entier : `cp -r . ../Prosperity_backup_$(date +%F)`
- [ ] Dormir 6h minimum

---

## T-0 : RELEASE DAY — PHASE 1 (0–30 min post CSV release)

### Étape 1 : download + analyze (5 min)

```bash
# Copier les CSV dans ROUND_2/
mkdir -p ROUND_2
cp ~/Downloads/*round_2* ROUND_2/

# Lancer l'analyse auto
python3 analyze_r2.py ROUND_2/
```

Lire `R2_ANALYSIS_REPORT.md`. Sections à scanner dans l'ordre :

1. **Produits + position limits** (du PDF R2 notice, à noter immédiatement)
2. **Section 1 Basic stats** → identifier stable / trending / volatile
3. **Section 3 Correlation matrix** → toutes paires avec `|corr| > 0.85`
4. **Section 5 Basket detection** → si un produit est r² ≥ 0.95 contre N autres
5. **Section 7 Quick interpretation** → verdict auto

### Étape 2 : classer la structure (10 min)

Pattern historique :

| Signature | Format R2 probable |
|---|---|
| 1 produit + observations (sunlight, tariff, foreign bid/ask) | **Cross-venue arb** (ORCHIDS-like, P2 R2) |
| 2 produits corr > 0.90, mid-range similaire | **Pair cointegration** (PINA/COCO, P1 R2) |
| 1 produit avec r² ≥ 0.95 contre 2–3 autres | **Basket / ETF arb** (GIFT_BASKET P2 R3 / PICNIC P3 R2) |
| Plusieurs produits indépendants | Probablement market making étendu (peu probable) |

### Étape 3 : confirmer via PDF notice (5 min)

- Si formule basket annoncée → **copier les poids exacts**
- Si observations mentionne sunlight/humidity/tariff → **cross-venue**
- Si juste "trade these products" → **utiliser ton analyse OLS**

**PIÈGE P2 R2 CONFIRMÉ** : sunlight/humidity étaient des distractions. L'alpha était dans tariffs/shipping. Ne pas perdre de temps sur les features exogènes sauf si elles entrent directement dans une formule de coût.

### Étape 4 : décision de template (5 min)

Ouvrir `trader_r2_template.py`, identifier le template à activer :

- **PAIR** → `PAIR_CONFIG["enabled"] = True`
- **BASKET** → `BASKET_CONFIG["enabled"] = True`
- **CROSS_VENUE** → `CROSS_VENUE_CONFIG["enabled"] = True`

Un seul template activé au début. Les autres restent False.

---

## T+30 à T+90 : PHASE 2 — CALIBRATION

### Si PAIR

1. Récupérer OLS coefficients de `R2_ANALYSIS_REPORT.md` section 4 :
   ```
   A = intercept + slope * B
   ```
2. Remplir dans `PAIR_CONFIG` :
   ```python
   "product_a": "<produit_y>",
   "product_b": "<produit_x>",
   "intercept": <OLS_a>,           # depuis rapport
   "slope": <OLS_b>,               # depuis rapport (ex: 1.875 si stable)
   "spread_mean": <moyenne_sample_spread>,  # calcul offline !
   "z_window": 45,
   "entry_z": 1.5,                 # P1 standard
   "exit_z": 0.3,
   "target_size_a": 40,
   "target_size_b": int(40 * slope),
   ```
3. Calculer `spread_mean` offline :
   ```bash
   python3 -c "
   import csv
   mids = {}
   # Lire CSV, calculer spread moyen sur tous les ticks
   # Dump la valeur à copier dans cfg
   "
   ```

### Si BASKET

1. Poids depuis PDF (ex : `PICNIC_BASKET1 = 6×CROISSANTS + 3×JAMS + 1×DJEMBES`)
2. Remplir `BASKET_CONFIG` :
   ```python
   "basket": "PICNIC_BASKET1",
   "components": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1},
   "intercept": 0.0,
   "spread_mean": <moyenne_offline>,   # CRITIQUE — hardcode depuis CSV
   "z_window": 45,                     # Linear Utility exact param
   "entry_z": 7.0,                     # Linear Utility exact
   "exit_z": 2.0,
   "target_basket_pos": 58,            # sur position_limit=60
   "hedge_components": False,          # P3: souvent mieux de NE PAS hedge
   ```

### Si CROSS_VENUE

1. Identifier foreign exchange dans observations (attribut `conversionObservations`)
2. Remplir `CROSS_VENUE_CONFIG` :
   ```python
   "product": "<ORCHIDS-like>",
   "edge_vs_foreign_ask": 2,          # Linear Utility exact
   "min_profit": 1.5,
   ```

---

## T+90 à T+150 : PHASE 3 — BACKTEST + TUNE

### Étape 1 : Copier v32 R1 logic dans le template (10 min)

Dans `trader_r2_template.py`, `trade_r1_product()` → copier le contenu exact
de `trade_product()` de `trader_v32.py`. Tester :

```bash
cp trader.py trader_v31_backup.py
cp trader_r2_template.py trader.py
python3 local_backtest_v3.py
# Doit donner ≥ +27,653 (R1 inchangé ; R2 non testable sans CSV R2 dans backtester)
cp trader_v31_backup.py trader.py  # RESTORE
```

### Étape 2 : Adapter `local_backtest_v3.py` pour R2 (15 min)

Si CSV R2 dispo, modifier `DAYS = [...]` et `DATA_DIR = "ROUND_2"`.

**Sanity** : faire tourner le template, vérifier que :
- R1 produits : PnL ≥ baseline
- R2 produits : signal_fires > 0 (pas silence complet)
- Aucune erreur dans les logs

### Étape 3 : Grid search (20 min)

Si PAIR : sweep `entry_z ∈ {1.0, 1.5, 2.0, 2.5, 3.0}`, prendre celui avec meilleur Sharpe.

Si BASKET : sweep `entry_z ∈ {3, 5, 7, 10, 15}`, prendre celui avec meilleur PnL + stabilité day-by-day.

**Méthodologie identique à v32 (cf `PROMPT_BACKTEST_METHODOLOGY.md`)** :
- Plateau (pas pic isolé)
- Sign-flip : `target_pos = -target_pos` doit donner PnL négatif
- Day-by-day : pas de jour qui explique > 70% du gain

### Étape 4 : Cap PnL drawdown (10 min)

Ajouter un kill-switch simple dans `Trader.run` :

```python
# Si cum_pnl_R2 < -5000 vs start → flatten all R2 positions
```

Ça évite une catastrophe si la strat rate complètement.

---

## T+150 à T+180 : PHASE 4 — SUBMIT

### Étape 1 : Flatten imports (5 min)

Concat `r2_primitives.py` dans `trader_r2_template.py` manuellement si
tu as encore des imports locaux. IMC n'accepte **que** le fichier
`trader.py` standalone + `datamodel.py` (fourni par eux).

### Étape 2 : Final sanity (5 min)

```bash
cp trader_r2_template.py trader.py
python3 -c "import ast; ast.parse(open('trader.py').read())"  # syntax
python3 local_backtest_v3.py  # R1 logic intact
md5 trader.py                 # noter pour traçabilité
```

### Étape 3 : Upload (2 min)

Upload sur la plateforme IMC. **Vérifier** :
- Le fichier est bien complet (pas tronqué)
- La version submittée = celle testée localement (même md5)

### Étape 4 : Monitor (pendant le round)

- Watch leaderboard
- Si score catastrophique → PATCH rapide (réduire `target_basket_pos`, flatten, ou disable R2 template)
- Si score bon → ne toucher à rien

---

## ANTI-PATTERNS (ne PAS faire)

1. **Over-fit 3 jours CSV** : la plateforme utilise d'autres jours pour le scoring. Matius Chong P3 a eu R2 qui marchait et R5 qui explosait à cause de ça.
2. **Pousser target à 100% du limit** : CarterT27 P3 a perdu R2. Toujours viser **limit - 2** minimum (Linear Utility = 58/60).
3. **Changer le code 30 min avant deadline** : les bugs-de-dernière-minute sont la cause #1 de catastrophe.
4. **Ignorer la méthode v31 R1** : elle score toujours sur les 5 rounds. Ne pas la casser.
5. **Trader plusieurs structures en même temps** : activer **un** template au début. Si budget > 50% atteint, réfléchir à empiler.

---

## RÉFÉRENCES RAPIDES

### Paramètres Linear Utility (P2 R3 basket) — REPRODUCIBLES
```python
default_spread_mean = 379.50439988484239   # HARDCODED
spread_std_window   = 45                    # ROLLING (court)
zscore_threshold    = 7                     # ENTRY
target_position     = 58                    # sur 60 limit
# Spread formula: basket_swmid - synthetic_swmid
```

### Paramètres nicolassinott (P1 R2 pair) — REPRODUCIBLES
```python
entry_z = 1.5
exit_z  = 0.5
# Spread = P_PINA - (15/8) * P_COCO    # ou simple 1:1
```

### Position limits historiques R2
- P3 R2 : CROISSANTS=250, JAMS=350, DJEMBES=60, PICNIC_BASKET1=60, PICNIC_BASKET2=100
- P4 R2 : TBD (lire le PDF)

### Top repos à consulter live (si bloqué)
- https://github.com/ericcccsliu/imc-prosperity-2 (P2 #2, basket params exacts)
- https://github.com/chrispyroberts/imc-prosperity-3 (P3 7th, allocation multi-basket)
- https://github.com/Sylvain-Topeza/imc-prosperity-3 (P3 top 1%, décomposition via basket2)

---

## FIN DU PLAYBOOK

Temps total estimé : 150–180 min depuis release CSV à submit final.
Si tu dépasses 180 min, submit la version la plus simple qui marche — **le simple submit > le perfect missed**.
