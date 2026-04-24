# P1 Follow-up IV Surface

## Q1 - Stabilité rolling / surface 2D
Verdict: GO. Rolling 500ts garde 5400 en edge long moyen 1.379 ticks et 5300 en edge short moyen 1.369 ticks. Le taux de positivité rolling 5400 long est 93.5%.
La hausse du coef quadratique est compatible avec le raccourcissement du TTE, mais 3 jours ne permettent pas de séparer proprement time decay et changement de régime informé. La surface 2D linéaire en T est fitable; voir `surface_2d_summary.csv`.

## Q2 - Fréquence des fills
Verdict: CAUTION. 5400 a 225 trades publics, taille moyenne 3.50; 5300 a 121 trades, taille moyenne 3.47. Build pair réaliste par jour via bid 5400 + ask 5300: ~0.3 contrats/jour.
Side mix: 5400 at-bid 100.0%, at-ask 0.0%; 5300 at-bid 98.6%, at-ask 0.2%. Le ratio book-depletion/public est un proxy noisy des prints non publics.

## Q3 - Résidu vs move VE
Verdict: TIMING INTELLIGENT. Résidu 5400 AR(1)=0.948; régression sur dS beta=-0.00010, t=-5.42, R2=0.001. Le timing par z-score/résidu est plus utile que trader à chaque tick.

## Q4 - Spread prix 5300 - 5400
Verdict: GO. Signal SHORT spread si spread > mean+sigma: EV/trade=0.474 ticks vs static short-spread PnL=-12.000 ticks sur 1 lot. Le spread est borné et fortement autocorrélé; l'entrée timée évite de payer le carry quand le spread est normal.

## Q5 - Sensibilité TTE
Verdict: GO. Baseline 7j x250: edge 5400 long=1.428, edge 5300 short=1.317. Les scénarios 5j/10j/365 gardent le signe; 250 jours avec decay intraday reste le plus plausible car l'IV ATM reste dans la zone 15-25%.

## Fichiers produits
- `rolling_surface_iv.csv`
- `rolling_surface_summary.csv`
- `surface_2d_summary.csv`
- `trade_flow_analysis.csv`
- `residual_regressions.csv`
- `residual_time_regimes.csv`
- `pair_spread_backtest.csv`
- `tte_sensitivity.csv`
- `rolling_surface_edges.png`
- `trade_flow_distribution.png`
- `residual_vs_dS.png`
- `residual_autocorr.png`
- `spread_5300_5400_timeseries.png`
- `tte_sensitivity.png`