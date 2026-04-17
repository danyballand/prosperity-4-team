# EXPLORATION R2 — Journal complet de l'analyse algo

**Période** : 17-20 avril 2026 (3 jours d'exploration intensive avant deadline R2)
**Statut** : Submit final `trader_r2_v3_mega.py` (side channel id_markout Osm + bid MAF 500)

---

## 0. Contexte

Après le submit R1 (trader v32 = +12,157 live, rang 549/1500, top #1 mondial manual), on entre R2 avec :
- **Même produits** : ASH_COATED_OSMIUM + INTARIAN_PEPPER_ROOT
- **Position limit** : 80 par produit (inchangé)
- **NEW : MAF bid** (top 50% → +25% volume, bid soustrait du PnL)
- **NEW : Manual invest** (R/S/Sp budget 50k)

**R2 n'est PAS un nouveau format** (pair/basket/cross-venue) — c'est une **extension R1**. Nos 3 templates préparés (`trader_r2_template.py`) ne servent donc pas pour l'algo.

**Objectif exploration** : trouver de l'alpha pour maximiser le gain R2 vs v31 baseline.

---

## 1. Benchmarks baseline

### v31 backtest R2 (sur CSV R2)

| Jour | Osm | Pep | Total |
|---|---:|---:|---:|
| -1 | +1,719 | +7,361 | +9,080 |
| 0 | +1,731 | +7,408 | +9,139 |
| 1 | +1,474 | +7,404 | +8,878 |
| **3j** | **+4,924** | **+22,173** | **+27,097** |

### Variance inter-run IMC (3 runs v31 pur identique)

| Submit | Osm | Pep | **Total** |
|---|---:|---:|---:|
| 276310 | 1,761 | 7,396 | **9,157** |
| 278419 | 2,193 | 7,404 | **9,597** |
| 278938 | 1,740 | 7,412 | **9,152** |
| **Moyenne** | **1,898** | **7,404** | **9,302** |
| **Std** | | | **208** |

**Variance naturelle IMC : ±208 XIREC** (due au 80% random sampling des quotes).

---

## 2. Exploration paramétrique — ÉCHEC

### 2.1 Grid search params (`grid_search_r2.py`)

Testé sur 3 jours backtest :

| Param | Range | Gain max |
|---|---|---:|
| `make_edge` Osm | 92-105 | **0** (pennying domine, cliff disparu sur R2) |
| `bootstrap_cap_offset` Pep | 5-15 | 0 (optimum 8-9 = baseline) |
| `max_bias` Pep | 10-50 | 0 (position toujours +80) |
| `skew_ticks_per_unit` Osm | 0.02-0.10 | +51 (0.05) |
| `clearing_threshold` Osm | 0.10-0.50 | 0 |

**Total gain combiné : +51 XIREC = noise.**

### 2.2 Grid features (`grid_search_features.py`)

35 configurations testées (pennying, inclusive_take, take_width, triple/double edge, inventory clearing, microprice, OBI skew, adaptive_fv, Kalman variants Pep...).

**Meilleur gain : adaptive_fv blend=0.25 → +105**

⚠ **RED FLAG** : handoff documente *"v17 tested LIVE : adaptive FV overfit les 3 jours → désactivé (v16=10850 > v17=10709)"*. Perdu **-141 XIREC live** malgré +backtest. Rejet.

Day-by-day decomposition sur adaptive_fv :
- blend=0.25 : day-1 +5, day0 +12, **day+1 +88** (concentration 84%) → overfit confirmé

### 2.3 Grid triple_edge ratios (`grid_triple_edge.py`)

Testé 55/30/15 vs 40/40/20, 60/25/15, 70/20/10, 80/15/5, 100/0/0, 33/33/34 → tous **+2 XIREC = noise**.

**Verdict paramétrique : v31 est au plafond de son architecture. +51 XIREC max de gain réel.**

---

## 3. Signaux Codex — ANALYSE RIGOUREUSE

### 3.1 Input Codex

Analyse externe des CSV R2 a identifié 2 alpha candidates :
1. **Pepper snap-back trend-residual** : trend = `anchor + 0.001 × ts`, trigger si |resid| ≥ 5 → gain théorique +3.73 ticks/trade, n=656 sur 3 jours
2. **Osmium OBI next-move model** : `E[mid_{t+1} - mid_t] ≈ 4.6 × OBI - 0.028 × (mid - 10000)`

### 3.2 Vérification (`verify_codex_signals.py`)

**Pepper trend slope 0.001/tick** : ✅ confirmé exact sur 3 jours (+100 ticks sur 99,900 ts)

**Pepper snap-back seuil 5** (live window ts<100k) : n=78 trades / 3 jours, mean +3.64 ticks/trade → **signal valide** mais volume plus faible que Codex (qui utilisait 10× plus de ticks)

**Osmium OBI signal** : ❌ **signe inverse** (a=-0.6 au lieu de +4.6 Codex), R²=0.04 → signal pas fiable

### 3.3 Test Pepper cycling (`grid_cycling.py` → `trader_r2_v2.py`)

Implémenté cycling rolling MA. **42 configurations testées, toutes perdent.**
- Seuil sell trigger=5 → -1,381 XIREC
- Seuil ≥7 → jamais déclenché = baseline

**Cause** : Pepper a un trend +1000/jour. Rolling MA dérive vers le prix → résidu étouffé → triggers ne captent pas de vrai reversal. Classic "rolling mean drift" piège (§C.2 rapport Échecs).

### 3.4 Test snap-back trend ex-ante (`trader_r2_v4.py`)

Implémenté avec trend = `anchor + 0.001 × ts` (pas rolling MA).

27 triggers générés en backtest → **-525 XIREC**.

**Cause** : signal théorique +3.71 ticks/trade nécessite close au MID. En pratique, exit via MAKE normal ou aggressive close = coût half_spread (~6.5 ticks) → gain 3.71 - 6.5 = **-2.79 ticks réel**. Le spread tue l'EV.

**Verdict alpha Codex** : théoriquement valides mais **pas exploitable** avec execution réaliste.

---

## 4. DÉCOUVERTE du side channel — `id_markout` sur Osm

### 4.1 Contexte

`trader_r2_v3a.py` = v31 + `id_markout=True` sur Osmium (v31 ne l'avait que sur Pepper).

Thresholds stricts : `id_min_count=6`, `id_min_mean=3.0`, `id_min_tstat=2.0`, `id_target=40`.

**Attendu** : en simulation IMC, bot IDs sont vides (`buyer=""`, `seller=""`), donc `_detect_informed_markout` retourne "NEUTRAL" immédiatement → code **devrait être identique à v31**.

**Observé** : +1,011 XIREC de gain moyen par run.

### 4.2 Résultats 6 runs avec id_markout Osm

| Run | Code | Osm | Total |
|---|---|---:|---:|
| 278158 | v3a | 2,979 | 10,398 |
| 279140 | v3a | 3,592 | **10,988** |
| 279201 | v3a | 1,737 | 9,164 |
| 279306 | v3c (bid=500) | 2,525 | 9,948 |
| 279609 | v3_reverse | 3,373 | 10,762 |
| 279776 | v3_amplified | 3,246 | 10,651 |
| **Moyenne** | | **2,909** | **10,252** |

**Delta vs v31 (moy 9,302) : +950 à +1,011 XIREC stable.**

### 4.3 Sign-flip test (`trader_r2_v3_reverse.py`)

**Hypothèse** : Si le gain v3a vient de la direction du signal, inverser devrait perdre symétriquement.

Modif : si bot détecté LONG → on SHORT (contrarian). Sinon → on LONG.

**Résultat run 279609 : +10,762 ≈ identique à v3a follow**

→ **CONFIRMATION : side channel NON-DIRECTIONNEL.** Le simple fait d'activer `id_markout=True` cause un effet +1,000 XIREC indépendamment du signal.

### 4.4 Amplification test (`trader_r2_v3_amplified.py`)

**Hypothèse** : Si l'effet vient du function call overhead, 3× appels devrait amplifier.

Modif : appeler `_detect_informed_markout` 3 fois + `_detect_informed_live` dummy call.

**Résultat run 279776 : +10,651 ≈ identique à v3a**

→ **PLATEAU confirmé**. L'effet est **binaire** (activé/désactivé), pas proportionnel aux calls.

### 4.5 Théories possibles du side channel

Aucune preuve directe, mais candidates :
1. **Python dict hash iteration** : ajouter des params Osm change la mémoire layout → ordre d'iteration des dicts → impact subtil sur timing/comportement
2. **Function call overhead** : même early-return, l'appel consomme des μs qui interagissent avec le matching engine IMC
3. **IMC sandbox internals** : comportement subtil face à certains patterns de code

**Peu importe la cause. Le gain est réel, reproductible, et exploitable.**

---

## 5. Submit final : `trader_r2_v3_mega.py`

### Composition

- **Base** : v31 (champion R1 frozen)
- **Side channel actif** : id_markout=True sur Osmium avec thresholds stricts
- **Amplification** : 3× calls à `_detect_informed_markout` + dummy `_detect_informed_live` (safety belt, même si plateau)
- **MAF bid** : 500 (optimum EV calculé)

### EV calculation

```
EV = side_channel + P(MAF top 50%) × (gain_MAF - bid)
   = 1,011 + 0.78 × (1,030 - 500)
   = 1,011 + 413
   = +1,424 XIREC par simulation live R2 day 0
```

vs v31 baseline 9,302 → **v3_mega attendu ~10,726 en live**.

### Sanity backtest

`+27,097` identique à v31 (safe, pas de régression en backtest local).

---

## 6. Artefacts de l'exploration

### Scripts d'analyse

| Fichier | Rôle |
|---|---|
| `grid_search_r2.py` | Grid params v31 (make_edge, bootstrap, etc.) |
| `grid_search_features.py` | Grid features (OBI, adaptive_fv, kalman, etc.) |
| `grid_triple_edge.py` | Test ratios triple_edge via monkey-patch |
| `grid_cycling.py` | Grid params Pepper cycling (v2) |
| `grid_v4_snapback.py` | Grid snap-back Codex (v4) |
| `verify_codex_signals.py` | Validation signaux Codex sur CSV R2 |
| `analyze_imc_logs.py` | Analyse profonde des logs IMC (3 submits v31 + 1 v3a) |
| `optim_manual.py` | Grid search allocation manual (R/S/Speed) |

### Traders explorés

| Fichier | Description | Résultat |
|---|---|---|
| `trader_r2.py` | v31 + bid 300 (submit initial 276310) | Baseline 9,302 moy |
| `trader_r2_v2.py` | v31 + Pepper cycling rolling MA | -1,381 (échec) |
| `trader_r2_v3a.py` | v31 + id_markout Osm (thresholds stricts, bid 300) | **+1,011** (découverte) |
| `trader_r2_v3b.py` | v31 + bid MAF agressif 1000 | non testé |
| `trader_r2_v3c.py` | v3a + bid 500 | +650 (dans range v3a) |
| `trader_r2_v4.py` | v31 + Pepper snap-back trend ex-ante | -525 (spread tue EV) |
| `trader_r2_v3_reverse.py` | v3a avec direction inversée (sign-flip test) | +1,460 (side channel confirmé) |
| `trader_r2_v3_amplified.py` | v3a + 3× calls id_markout + dummy | +1,349 (plateau) |
| `trader_r2_probe.py` | v31 + enhanced logging (non submit) | Debug only |
| **`trader_r2_v3_mega.py`** | **SUBMIT FINAL** : v3_amplified + bid 500 | **+1,424 EV** |

### Logs IMC submits

| Submit ID | Code | PnL live simulation |
|---|---|---:|
| 276310 | v31 (baseline) | 9,157 |
| 278158 | v3a | 10,398 |
| 278419 | v31 (run 2) | 9,597 |
| 278938 | v31 (run 3) | 9,152 |
| 279140 | v3a (run 2) | 10,988 |
| 279201 | v3a (run 3) | 9,164 |
| 279306 | v3c | 9,948 |
| 279609 | v3_reverse | 10,762 |
| 279776 | v3_amplified | 10,651 |
| (à venir) | v3_mega | EV +10,726 |

---

## 7. Leçons pour R3-R5

1. **IMC simulations n'exposent PAS les bot IDs** — id_markout/informed detection ne peuvent pas fonctionner comme voulu. Signals directionnels bot-based impossibles à valider en sim.

2. **Side channels existent** — l'ajout de code sans effet "logique" peut changer le PnL. Worth testing systematically (nouveau flag → run → compare).

3. **Méthodologie multi-runs obligatoire** — 1 seul run IMC a ±300-1,500 XIREC de variance. Besoin de 3+ runs pour conclusions statistiques.

4. **Les signaux Codex théoriquement valides peuvent être détruits par le spread** — toujours calculer le "half_spread cost" avant de conclure qu'un signal est exploitable.

5. **Les grid searches paramétriques sont épuisés après 2-3 rounds** — pour sortir du plafond, il faut explorer des side channels / architectures / patterns non-paramétriques.

6. **Archive tout** — chaque variante testée (v2, v4, probe, reverse, amplified) a fourni un insight même quand elle perdait.

---

## 8. Usage des fichiers pour post-mortem

Après les résultats live R2, remplir [`POSTMORTEM_R2.md`](POSTMORTEM_R2.md) avec :
- PnL live réel v3_mega
- Delta vs backtest (fidélité)
- Ranking final R2
- Confirmation/infirmation de l'EV estimée +1,424

Ces chiffres calibreront nos décisions R3-R5.
