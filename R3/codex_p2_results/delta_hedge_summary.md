# P2 Delta hedge - resume

Hypotheses: TTE lineaire de 7 jours a day=0,timestamp=0, r=0, edge IV P1 non trouve donc edge brut fallback = 1 tick/VEV. Les deltas empiriques sont estimes par regression sans intercept dC = beta*dS, sur returns de mid-price et sans lier les fins/debuts de jour.

## Lecture prioritaire
Le pic de correlation reste surtout synchrone ou VE-lead; pas de signal VEV-leads robuste selon le seuil uplift > 0.02.

## Strikes hedgables avec VE
Les hedges les plus propres par stabilite/R2 sont: VEV_5300, VEV_5200, VEV_5100, VEV_5000, VEV_4500. Les deltas les plus instables empiriquement sont: VEV_4000 (std_roll=0.090), VEV_4500 (std_roll=0.076), VEV_5000 (std_roll=0.060). VEV_6000/VEV_6500 sont statiques dans ces books: cout faible, mais pas de signal exploitable.

## Ratios et couts pour 50 VEV
- VEV_5400: short VE=6, delta=0.129, cout_exec=40.00, net_edge_assume=-2.50, lag=0, signal=sync_no_lead_signal, stabilite=stable.
- VEV_5300: short VE=14, delta=0.273, cout_exec=85.00, net_edge_assume=-47.50, lag=0, signal=sync_no_lead_signal, stabilite=stable.
- VEV_5200: short VE=22, delta=0.437, cout_exec=130.00, net_edge_assume=-92.50, lag=0, signal=sync_no_lead_signal, stabilite=stable.
- VEV_5100: short VE=29, delta=0.577, cout_exec=172.50, net_edge_assume=-135.00, lag=0, signal=sync_no_lead_signal, stabilite=stable.
- VEV_5000: short VE=33, delta=0.653, cout_exec=232.50, net_edge_assume=-195.00, lag=0, signal=sync_no_lead_signal, stabilite=stable.

Un swing delta de 0.1 sur 50 options implique de retrader 5 VE par 10 timestamps, avant meme de tenir compte du swing empirique.

## Cross-VEV hedging
Aucune paire VEV avec correlation de returns > 0.95 n'a ete detectee.

Fichiers principaux: delta_empirical.csv, lead_lag.csv, hedge_recommendations.csv, vev_pairwise_hedges.csv et les quatre PNG demandes.
