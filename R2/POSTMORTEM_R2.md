# POST-MORTEM R2 — à remplir dès que les résultats IMC tombent

**Date submit** : ___________  
**Date résultats** : ___________

---

## 1. Résultats live IMC

### Algo "Limited Market Access"
| Metric | Valeur | Notes |
|---|---:|---|
| PnL brut algo R2 live | _______ | avant déduction MAF |
| MAF bid accepté ? | □ OUI  □ NON | top 50% des bidders ? |
| MAF bid payé | _______ | 300 si accepté, 0 sinon |
| **PnL net algo R2** | **_______** | brut − bid |
| Rang algo R2 | _______ ième | |

### Manual "Invest & Expand"
| Metric | Valeur | Notes |
|---|---:|---|
| Allocation soumise | R=15 / S=45 / Sp=40 | (ou ajusté : _____) |
| Research output | _______ | attendu ≈ 120,152 |
| Scale output | _______ | attendu = 3.15 |
| Speed multiplier | _______ | = rank réel (optim=0.9 / med=0.62 / pes=0.47) |
| Budget utilisé | 50,000 | |
| **PnL manual R2** | **_______** | R × S × Sp − 50,000 |
| Rang manual R2 | _______ ième | |

### Total Phase 1 (R1 + R2)
| | Valeur | Attendu |
|---|---:|---:|
| Total R1 | 186,931 | (déjà acquis) |
| Total R2 | _______ | estimé +152k à +302k |
| **Grand total Phase 1** | **_______** | seuil qualif : 200,000 |
| Qualifié Phase 2 ? | □ OUI  □ NON | (>= 200k) |
| Rang global Phase 1 | _______ ième | R1 était 549 |

---

## 2. Analyse des écarts backtest → live

### Algo
| | Backtest day 0 | Live day 0 | Ratio réalisé | Ratio R1 (rappel) |
|---|---:|---:|---:|---:|
| Osmium | +1,731 | _______ | _______ | 41% |
| Pepper | +7,408 | _______ | _______ | 99.6% |
| MAF gain | +425 sim | _______ | _______ | n/a |

### Manual — rank Speed réel
- Distribution adversaire observée (si visible) : __________
- Notre rang Speed (investment 40%) : ______ ième
- Scénario réalisé : □ optimistic (rank≈0.9)  □ median (rank≈0.62)  □ pessimistic (rank≈0.47)  □ autre : _____

---

## 3. Bombes qu'on a évitées (check vs rapport Échecs)

| Piège | §Rapport | Risque | Résultat |
|---|---|---|---|
| Position limit overshoot (FOK) | A.1 | Rejet total ordre | □ évité  □ rencontré |
| traderData > 49k chars | A.2 | Crash silencieux | □ évité  □ rencontré |
| state.position[p] KeyError | A.4 | Crash run() | □ évité  □ rencontré |
| self.xxx pas persisté AWS | A.3 | State reset silent | □ évité  □ rencontré |
| Hotfix < 30 min deadline | D.1 | Bug introduit | □ évité  □ rencontré |
| Amnésie post-R2 (casser R1) | D.2 | Perte acquis R1 | □ évité  □ rencontré |

---

## 4. Leçons pour R3

(à remplir une fois les résultats connus)

### Ce qui a marché
- 

### Ce qui n'a pas marché
- 

### Décisions paramètres pour R3
- Ajuster bid() ? (garder 300 si accepté top 50%, remonter si trop de teams au-dessus)
- Ajuster allocation manual si R3 a aussi un challenge manual
- Tenir v31/trader_r2 inchangé pour continuer à scorer sur Osm/Pep

### Rang global (Phase 2 en tête)
- Si qualifié Phase 2 : focus sur remonter du top 500 vers top 100
- Gap attendu avec top (probablement ~200k à combler) → R3/R4/R5 critiques

---

## 5. Notes libres

_____________
