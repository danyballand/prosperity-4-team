# R3 "Gloves Off" — Session de recherche d'alpha

**Date :** 2026-04-25
**Équipe :** LYON (Dany)
**Objectif initial :** identifier et combler le gap (+100k SS) vs top teams sur la fenêtre live R3 (jour 2 / 0–100k ticks).
**Résultat final :** **v12 = +22,776 SeaShells** confirmé live (4 reproductions identiques). Aucun patch additionnel testé n'a dépassé ce baseline en live.

---

## 1. Contexte et baseline

- Le **live R3 tourne sur jour 2 / ts 0–99,900** (data publique day 2 sur fenêtre 100k ticks).
- Profit live = 100% déterministe pour un même code.
- Baseline pré-session : **v6 (+3,806 live)** — essentiellement HYD MM passif + adaptive FV, VE wall_mid, VEV ITM MM passif, VEV OTM disabled.
- Le score "UI Prosperity" inclut le baseline ~360k (XIRECS / cumul) + le profit R3 généré.

## 2. Findings principaux (chronologique)

### Phase 1 — Diagnostic des biais

| Trouvaille | Impact | Statut |
|---|---|---|
| Live tourne sur jour 2 / 0–100k seulement, pas 1M | recadre toute l'optimisation | confirmé |
| Backtest 3j × 1M = INDICATEUR FAIBLE du live | les gains 3d ne se traduisent pas linéairement | confirmé |
| Backtest jour2_100k = proxy direct du live à ~30% près | seul backtest pertinent | confirmé |
| HYD limit > 200 → rejets serveur | wiki R3 cap strict | confirmé via 400398 (367 rejets) |
| `log_bot_autopsy=True` causait spam → désactivé | cleanup safety | appliqué |

### Phase 2 — HYD regime (alpha asymétrique, autopsie 369858)

L'audit du pote a révélé que **HYD aggressive buys = -19 ticks markout à h+10k** (TOXIQUE), tandis que **HYD mid<9950 + mom>0 → +27 ticks markout, win 88.9%**.

→ **v9 HYD regime-based** : SHORT si mid≥10010, LONG_CAP si mid<9950+mom>0, AVOID si 9970-10010+mom<0, NEUTRAL_MM sinon.

**Live confirmé : v9 = +16,385 (gain +12,579 vs v6).**

### Phase 3 — SHORT_LITE anti-bot-buy (le vrai alpha trouvé)

Diagnostic du log live 400892 : 10 trades anonymes AT_ASK sur HYD, **mo10k mean = -34.5** (= bots qui achètent perdent ~34 ticks dans les 10k ticks suivants).

→ **v12 SHORT_LITE** : si dans regime AVOID/NEUTRAL_MM et un bot lift l'ask (`buyer != "SUBMISSION"` et `tr.price >= mid`), upgrade en SHORT_LITE → vendre 30 unités au best_bid.

**Live confirmé : v12 = +22,776 (gain +6,391 vs v9). Reproduit 4 fois exactement (401365, 402921, 409162, et v23 inactif).**

## 3. Ce qui NE MARCHE PAS en live

| Tentative | Hypothèse | Backtest | Live | Verdict |
|---|---|---|---|---|
| **v11 lim=300** | wiki ≠ vrai limit | +28,702 | +15,786 (-7k) | rejets serveur stricts à 200 |
| **v14 hardened** | filter `seller==SUBMISSION skip` (Codex audit anti self-trigger) | +16,565 | **+10,767 (-12,009)** | filtre supprime le signal le plus précieux (un bot lift NOTRE ask = signal SHORT exact) |
| **v15 multi-taker** | IV smile taker sur V5300/5400/5500 | +132 | -6 | biais IV trop faibles sur 100k |
| **v16 LONG_LITE** | symétrique au SHORT_LITE | -103 | non testé | backtest 3d -12k, abandonné |
| **v17 multi-level** | vendre top 3 bids | +2,597 | **+20,323 (-2,453)** | dégrade exécution : avg_sell baisse 2.5 ticks, avg_buy monte 4 ticks → spread perd 6.6 ticks/cycle |
| **v18 IV multi-scalp** | Z-score residual + outliers (briefing R3 Rook-E1) | -272k 3d | non submitté | adverse selection brutale |
| **v22 max aggressive** | tout empilé | +18,946 | **+19,410 (-3,366)** | combos ne se cumulent pas, certains dégradent |
| **v23 5400_sell** | Codex finding : seul signal IV crossing positif | identique v12 | identique v12 (signal jamais activé) | smile_FV jamais < bid sur jour2 100k |
| **v34 combo clean** | LONG_LITE + BIG_SIGNAL + 4000 inside | +17,129 | **+21,625 (-1,151)** | LONG_LITE/BIG_SIGNAL foirent en live |
| **v33 ultra** | tout + post_avoid_long | -10,374 backtest | **+5,880 (-16,896)** | post_avoid_long catastrophique |
| **OTM long-bid 5400/5500** | absorber bot dump | +38 | 0 fills | queue priority kills |
| **VEV ITM penny edge=1** | Codex passive markout +6.56 | -45 à -60 | non submitté | adverse selection même sans haircut |
| **VE contrarian** | mom_5 > 5 → SHORT, < -5 → LONG | 0 | non submitté | target_bias n'a pas d'effet structurel sur VE (skew=0, inv_clearing=False) |
| **VE skew + inv_clearing** | cycles VE plus rapides | -467 | non submitté | dégrade VE PnL |
| **HYD limit boost (250-400)** | plus de capacité | +7,246 backtest | rejets serveur | impossible |
| **HYD make_edge réduit** | quoter dans le range 9915-10031 | 0 effet | non submitté | regime override la logique normale |

## 4. Versions live testées (résumé chronologique)

| Submit ID | Version | Profit | Δ vs v12 |
|---|---|---|---|
| (early) | v6 baseline | +3,806 | -18,970 |
| (early) | v9 regime | +16,385 | -6,391 |
| **401365** | **v12 SHORT_LITE** | **+22,776** | **★ baseline** |
| **402921** | v12 reproduce | +22,776 | 0 (déterministe) |
| **409162** | v23_5400_sell | +22,776 | 0 (signal pas activé) |
| 405873 | v17 multi-level | +20,323 | -2,453 |
| 406615 | v23 multi-level | +20,278 | -2,498 |
| 406049 | v22 max | +19,410 | -3,366 |
| 409359 | v34 combo clean | +21,625 | -1,151 |
| 401755 | v14 hardened | +10,767 | -12,009 |
| 409535 | v33 ultra | +5,880 | -16,896 |
| 400398 | v11 lim=300 | +15,786 | -6,990 (rejets serveur) |

## 5. Pistes RECHERCHÉES via mega-tests (60+ variantes backtest)

Sur 60+ variantes testées, AUCUNE n'a dépassé v17 backtest +19,744 de plus que +24 SeaShells (= noise) :
- VEV ITM edge sweep (1-4) → -45 à -60
- VE config (skew/clearing) → -467 à -5,422
- SHORT_LITE size sweep → cap par volume du best_bid
- OTM price-improve (5400/5500) → ~0
- HYD make_edge sweep → 0 effet
- VEV ITM lim boost → -30 à -60
- HYD combo size+edge → 0
- VE aggressive (skew=0.05+) → -470 à -5,422
- VEV synth taker (4000+4500) → +24 à -45
- Ultimate combo → -512

## 6. Pourquoi le gap +100k vs top teams reste non comblé

Hypothèses (non vérifiables sans replays publics post-R3) :
1. **Stratégies cross-product / signal hidden** que notre simulateur ne reproduit pas.
2. **Détection de bots informés via IDs** non disponibles en R3 (buyer/seller souvent vides).
3. **Auction dynamics ou patterns timing** non capturés par market_trades publiques.
4. **Manuel + R1/R2 cumul** plutôt qu'alpha R3 algo seul.

Le briefing R3 "Rook-E1" suggère IV smile + moneyness + outliers comme stratégie principale. Notre v18 IV multi-scalp a tenté précisément ça → -272k backtest 3d, abandonné. Le briefing théorique ne se vérifie pas en pratique avec notre simulateur.

## 7. Code final retenu — `trader_r3_v12_pure.py`

```python
# HYD : regime + SHORT_LITE single-level
"hyd_regime": True,
"hyd_regime_size": 50,
"hyd_regime_short_thresh": 10010,
"hyd_regime_long_thresh": 9950,
"hyd_regime_mom_window": 5,
"hyd_short_lite_size": 30,
"hyd_long_lite_enable": False,  # désactivé : dégrade en live
"hyd_big_signal": False,
"hyd_post_avoid_long": False,    # ❌ catastrophique en live (-17k)

# VE : config inchangée v6 (skew=0, inv_clearing=False)

# VEV ITM (4000-5100) : MM passif standard, edge 5/2
# VEV OTM (5200-6500) : disabled (limit=0)
```

**Logique SHORT_LITE :**
- Dans regime AVOID/NEUTRAL_MM
- Filtre `buyer != "SUBMISSION"` (CRITIQUE : ne PAS ajouter `seller != "SUBMISSION"` filter — testé v14 = -12k régression)
- Si trade au-dessus du mid actuel et qty ≥ 2 → SHORT 30 unités au best_bid

## 8. Fichiers de la session

### Code principal
- `trader_r3.py` — code de production avec v12 SHORT_LITE + flags conditionnels pour autres patches
- `trader_r3_v12_pure.py` — version définitive à submit (= 22,776 confirmé)
- `trader_r3_v23_5400_sell.py` — v12 + 5400 SELL crossing (signal jamais activé en live)
- `trader_r3_v25_long_lite.py` — v12 + LONG_LITE (test isolé, non submitté)
- `trader_r3_v28_big_signal.py` — v12 + BIG_SIGNAL qty≥5 (non submitté)
- `trader_r3_v29_post_avoid.py` — ❌ DANGEREUX (HYD -11k backtest, -17k live confirmé via v33)
- `trader_r3_v31_4000_inside.py` — v12 + VEV_4000 inside aggressive (non submitté)
- `trader_r3_v32_combo_audacious.py` — ❌ contient post_avoid → DANGEREUX
- `trader_r3_v33_ultra.py` — ❌ submit 409535 = +5,880 (-16k catastrophe)
- `trader_r3_v34_combo_clean.py` — submit 409359 = +21,625 (-1k régression)
- `build_versions.py` — générateur de versions

### Tests / audits
- `audit_day2_100k.py` — analyse marché jour 2 100k
- `rolling_window_audit.py` — drawdown rolling fenêtres 10k-200k
- `test_window_0_100k.py` — confirme jour 2 0-100k = fenêtre live
- `test_hyd_regime.py` / `test_hyd_regime_sweep.py` — sweep seuils HYD
- `test_hyd_make_edge.py` — sweep make_edge HYD
- `test_hyd_patch.py` — patches défensifs HYD
- `test_v10_combo.py` / `test_v11_combo.py` — combos HYD+VE+VEV
- `test_ve_contra_fixed.py` — VE contrarian avec mid_now
- `test_multi_taker.py` — multi-strike taker additivité
- `test_4500_overlay.py` — VEV_4500 overlay sur MM
- `test_more_angles.py` / `test_more_push.py` / `test_mega_push.py` / `test_exotic_push.py` — mega tests

### Scripts iv quoting / scalping (existants)
- `iv_quoter.py` — Black-Scholes + smile fit leave-one-out
- `iv_surface.py` — fit quadratic + IVSurfaceTracker (Z-score EMA)
- `bs_pricing.py` — Black-Scholes vanilla
- `diagnose_iv_smile.py` — diagnostic résidu IV par strike

## 9. Conclusion / decision tree pour R4

1. **Pour R3 final : submit `trader_r3_v12_pure.py`** = +22,776 confirmé.
2. **Bio-Pods manuel** = +4-5k SS additionnels (pick recommandé : 760, 850 AGRO ou 755, 840 ULTRA).
3. **Pour R4 :** ne PAS optimiser sur backtest 3j × 1M, optimiser sur fenêtre live spécifique.
4. **Pour R4 :** intégrer log_bot_autopsy dès le départ, analyser les patterns de bots avant de coder l'alpha.
5. **Pour R4 :** éviter les patches qui dépendent de filtres `seller=SUBMISSION` ou similaire (testés foirent).
6. **Pour R4 :** SHORT_LITE single-level sur best_bid uniquement (multi-level dégrade exécution).

---

**Bilan honnête :** ~10 submits live consommés, 60+ variantes backtest testées, **+6,391 SeaShells de gain réel vs v9 baseline trouvés via SHORT_LITE**. Tous les autres patches théoriquement défendables (briefing R3 Rook-E1, audit pote, Codex deep scan) ne se vérifient pas en live sur cette fenêtre 100k.

**Le gap +100k vs top teams reste non expliqué et probablement non comblable sans information additionnelle (replays post-R3).**
