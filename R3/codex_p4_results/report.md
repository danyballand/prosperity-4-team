# R3 Spreads, baskets & stat arb multi-produits

## Résumé exécutif
- Butterfly: 0 violations de convexité au mid, 0 violations exécutables au bid/ask sur les triplets adjacents.
- Meilleure paire co-intégrée: VEV_4000 / VEV_4500 (tADF=-123.42, p≈0.0010, beta=1.0001, EV≈-52.105 ticks/trade).
- Meilleure paire par EV net parmi les co-intégrées positives: VEV_5000 / VEV_5400 (EV≈8.614 ticks/trade, p≈0.0022).
- Synthétique VE: meilleur signal VEV_4500 vs VELVETFRUIT_EXTRACT avec edge max exécutable 1.000 ticks.

## Réponses aux 3 questions prioritaires
1. Violations butterfly persistantes: non. Aucune violation mid ni bid/ask détectée sur les triplets adjacents.
2. Paires VEV: VEV_4000 / VEV_4500 est la plus robuste par p-value approx (tADF=-123.42, p≈0.0010); EV net estimé -52.105 ticks/trade. La meilleure EV positive est VEV_5000 / VEV_5400 à 8.614 ticks/trade.
3. Réplication synthétique VE: oui. Le meilleur test est synthetic_deep_itm (VEV_4500), fréquence 0.333/jour, edge max 1.000.

## Calls ou puts
Les VEV se comportent comme des calls: les prix baissent avec le strike et les corrélations de returns avec VE sont globalement positives ou nulles pour les options quasi mortes (min=0.348, max=0.765). Pas de put caché détecté.

## Top 5 actionnable
1. **cointegration_pair** VEV_5000 VEV_5400  - direction: short residual VEV_5000 - beta*VEV_5400 when high; EV=8.614; freq=0.333/jour; capital≈298.361; worst=8.614. mean_abs_resid=8.840, std_resid=11.030, sharpe_proxy=6.904
2. **cointegration_pair** VEV_4500 VEV_5400  - direction: short residual VEV_4500 - beta*VEV_5400 when high; EV=3.497; freq=0.667/jour; capital≈791.743; worst=-1.139. mean_abs_resid=10.332, std_resid=12.816, sharpe_proxy=2.819
3. **cointegration_pair** VEV_5000 VEV_5500  - direction: long residual VEV_5000 - beta*VEV_5500 when low; EV=2.996; freq=0.667/jour; capital≈286.172; worst=2.162. mean_abs_resid=9.663, std_resid=11.865, sharpe_proxy=2.440
4. **cointegration_pair** VEV_5100 VEV_5400  - direction: short residual VEV_5100 - beta*VEV_5400 when high; EV=3.624; freq=0.333/jour; capital≈213.203; worst=3.624. mean_abs_resid=6.539, std_resid=8.300, sharpe_proxy=2.855
5. **theta_calendar_proxy** VEV_4000   - direction: short after under-decay; EV=51.500; freq=0.333/jour; capital≈1295.000; worst=n/a. low-confidence theta-only proxy; underlying move is not delta-adjusted

## Pseudo-code des stratégies
```python
# 1) Butterfly convexity
fly = w1*C[K1] - C[K2] + w3*C[K3]
if zscore(fly) < -2 and entry_cost + exit_cost < expected_reversion:
    buy(w1, C[K1]); sell(1, C[K2]); buy(w3, C[K3])
if zscore(fly) > 0: close_all()

# 2) Co-integration pair
resid = C[K1] - beta*C[K2] - intercept
if resid > mean + 2*std: sell(C[K1]); buy(beta, C[K2])
if resid < mean: close_all()

# 3) Synthetic VE
synth = C[4000] + 4000
if bid(VE) - ask(C[4000]) - 4000 > cost: buy(C[4000]); sell(VE)
if abs(synth - VE) reverts through mean: close_all()

# 4) HYD guard
if rolling_corr(HYD, VE_or_VEV) < 0.3: do not pair HYD with VE complex

# 5) Theta proxy
theta_decay = C_prev - BS(S_prev, K, iv_prev, T_prev - 1/365)
if realized_decay - theta_decay > spread: buy over-decayed call
```

## HYD pair-trade
| product  | return_corr_with_HYD | max_abs_rolling_corr_250 | pair_trade_candidate |
| -------- | -------------------- | ------------------------ | -------------------- |
| VEV_5300 | 0.005                | 0.253                    | False                |
| VEV_4000 | 0.002                | 0.239                    | False                |
| VEV_4500 | 0.002                | 0.231                    | False                |
| VEV_5500 | 0.003                | 0.218                    | False                |
| VEV_5400 | 0.006                | 0.216                    | False                |

## Theta proxy
| product_a | day_pair | direction               | realized_decay | bs_theta_decay | edge_after_spread |
| --------- | -------- | ----------------------- | -------------- | -------------- | ----------------- |
| VEV_6000  | 0->1     | short after under-decay | 0.000          | 0.261          | -1.261            |
| VEV_6500  | 0->1     | short after under-decay | 0.000          | 0.276          | -1.276            |
| VEV_6000  | 1->2     | short after under-decay | 0.000          | 0.292          | -1.292            |
| VEV_6500  | 1->2     | short after under-decay | 0.000          | 0.308          | -1.308            |
| VEV_5500  | 0->1     | short after under-decay | 1.000          | 2.047          | -2.047            |
| VEV_5500  | 1->2     | short after under-decay | -0.500         | 2.082          | -4.582            |
| VEV_5400  | 0->1     | short after under-decay | -0.500         | 3.189          | -5.689            |
| VEV_5400  | 1->2     | short after under-decay | -3.000         | 3.642          | -8.642            |
| VEV_5300  | 0->1     | short after under-decay | -5.000         | 5.034          | -12.034           |
| VEV_5300  | 1->2     | short after under-decay | -6.000         | 5.780          | -13.780           |
| VEV_5200  | 0->1     | short after under-decay | -7.000         | 5.122          | -15.122           |
| VEV_5100  | 0->1     | short after under-decay | -13.500        | 3.568          | -22.068           |

## Meilleures p-values co-intégration
| product_a | product_b | beta  | pvalue_approx | EV_par_trade | opportunities_per_day | risk_max_ticks |
| --------- | --------- | ----- | ------------- | ------------ | --------------------- | -------------- |
| VEV_4000  | VEV_4500  | 1.000 | 0.001         | -52.105      | 92.000                | -56.004        |
| VEV_4000  | VEV_5000  | 1.083 | 0.001         | -27.669      | 30.333                | -39.081        |
| VEV_4500  | VEV_5000  | 1.083 | 0.001         | -18.759      | 16.333                | -32.749        |
| VEV_5400  | VEV_5500  | 1.856 | 0.001         | -3.636       | 0.333                 | -3.636         |
| VEV_5200  | VEV_5300  | 1.523 | 0.001         | -6.641       | 0.667                 | -7.345         |
| VEV_5100  | VEV_5200  | 1.299 | 0.001         | -12.191      | 0.333                 | -12.191        |
| VEV_5300  | VEV_5500  | 3.068 | 0.001         | -2.544       | 1.667                 | -3.771         |
| VEV_4000  | VEV_5100  | 1.181 | 0.001         | -17.021      | 1.000                 | -17.722        |
| VEV_5300  | VEV_5400  | 1.626 | 0.001         | -1.925       | 1.000                 | -2.509         |
| VEV_5100  | VEV_5300  | 1.932 | 0.001         | -5.924       | 0.667                 | -8.022         |
| VEV_5200  | VEV_5500  | 4.340 | 0.001         | 0.305        | 1.000                 | -0.362         |
| VEV_5000  | VEV_5100  | 1.109 | 0.001         | n/a          | 0.000                 | n/a            |

## Artefacts
- `arb_opportunities.csv` : classement unique de toutes les opportunités.
- `fly_daily_stats.csv` : table demandée par triplet et jour.
- `fly_timeseries_by_triplet.png`
- `correlation_matrix.png`
- `synthetic_ve_vs_real.png`
- `cointegration_pvalues_matrix.png`

## Limitations
- Les p-values co-intégration sont une approximation ADF/Engle-Granger interne, suffisante pour classer les paires mais pas pour une inférence académique stricte.
- Les tests theta sont des proxys à partir de l'IV implicite estimée; la variation de spot peut dominer le theta pur.
- Les edges butterfly signalés au mid peuvent être du bid-ask bounce; le champ `tradable_arb_count` filtre les cas exécutables.