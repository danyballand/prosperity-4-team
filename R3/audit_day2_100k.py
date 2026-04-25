"""
Audit complet jour 2 ts 0-99900 :
  1. Mouvements de prix par produit (volatilité, drift, range)
  2. Volume tradé par produit, prix moyens BUY vs SELL
  3. Maximum theoretical PnL par produit (achete bottom, vend top)
  4. Comparison avec ce que v6 fait

Objectif : identifier où sont les +100k que les tops captent.
"""
import os, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DATA = os.path.join(HERE, "data")
PRICES = os.path.join(DATA, "prices_round_3_day_2.csv")
TRADES = os.path.join(DATA, "trades_round_3_day_2.csv")
MAX_TS = 100_000

# Load prices
products_data = {}  # product -> list of (ts, mid, bb, ba, bv, av)
with open(PRICES, 'r') as f:
    rdr = csv.reader(f, delimiter=';')
    header = next(rdr)
    for row in rdr:
        if not row or len(row) < 17:
            continue
        try:
            day = int(row[0]); ts = int(row[1]); product = row[2]
            if ts >= MAX_TS:
                continue
            bb1 = int(row[3]) if row[3] else 0
            bv1 = int(row[4]) if row[4] else 0
            ba1 = int(row[9]) if row[9] else 0
            av1 = int(row[10]) if row[10] else 0
            mid = float(row[15]) if row[15] else 0.0
            products_data.setdefault(product, []).append((ts, mid, bb1, ba1, bv1, av1))
        except Exception:
            continue

# Load trades
trades_data = {}
with open(TRADES, 'r') as f:
    rdr = csv.reader(f, delimiter=';')
    header = next(rdr)
    for row in rdr:
        if not row or len(row) < 7: continue
        try:
            ts = int(row[0]); buyer = row[1]; seller = row[2]
            product = row[3]; price = float(row[4]); qty = int(row[5])
            if ts >= MAX_TS:
                continue
            trades_data.setdefault(product, []).append((ts, price, qty, buyer, seller))
        except Exception:
            continue

print("=" * 100)
print(f"AUDIT JOUR 2 ts 0-{MAX_TS:,} — où est l'alpha de +100k ?")
print("=" * 100)

print(f"\n{'Product':<24s}  {'mid_open':>9s}  {'mid_close':>9s}  {'min':>8s}  {'max':>8s}  "
      f"{'range':>7s}  {'std_pct':>7s}  {'n_trades':>8s}  {'tot_vol':>8s}  {'max_PnL_perfect':>16s}")

results = []
for product in sorted(products_data.keys()):
    pdata = sorted(products_data[product])
    if len(pdata) < 2:
        continue
    mids = [d[1] for d in pdata if d[1] > 0]
    if not mids:
        continue
    mid_open = mids[0]
    mid_close = mids[-1]
    mid_min = min(mids)
    mid_max = max(mids)
    rng = mid_max - mid_min
    mean_mid = sum(mids) / len(mids)
    std_pct = (sum((m - mean_mid)**2 for m in mids) / len(mids))**0.5 / mean_mid * 100 if mean_mid > 0 else 0

    trades = trades_data.get(product, [])
    n_trades = len(trades)
    tot_vol = sum(abs(t[2]) for t in trades)

    # Max theoretical PnL : achète au min global, vend au max global, taille = position_limit
    # Et en plus capture chaque mouvement intermédiaire de magnitude importante
    # Approx simple : (max - min) × position_limit
    plim = {"HYDROGEL_PACK": 200, "VELVETFRUIT_EXTRACT": 200}.get(product, 300)
    max_pnl_perfect = rng * plim

    results.append((product, mid_open, mid_close, mid_min, mid_max, rng, std_pct,
                    n_trades, tot_vol, max_pnl_perfect))
    print(f"  {product:<22s}  {mid_open:>9.1f}  {mid_close:>9.1f}  {mid_min:>8.1f}  {mid_max:>8.1f}  "
          f"{rng:>7.1f}  {std_pct:>6.2f}%  {n_trades:>8d}  {tot_vol:>8d}  {max_pnl_perfect:>+16,.0f}")

print()
print("=" * 100)
print("TOP 5 produits par PnL maximum théorique (range × position_limit) :")
print("=" * 100)
top = sorted(results, key=lambda r: -r[9])[:5]
for product, _, _, mn, mx, rng, std, _, _, max_pnl in top:
    print(f"  {product:<22s}  range {mn:.1f}→{mx:.1f}  ({rng:.0f} ticks, std {std:.2f}%)  "
          f"max théorique {max_pnl:+,.0f}")

print()
print("=" * 100)
print("VOLUME TRADÉ PAR PRODUIT (le marché bouge où ?) :")
print("=" * 100)
top_vol = sorted(results, key=lambda r: -r[8])[:10]
for product, _, _, _, _, _, _, n_trades, tot_vol, _ in top_vol:
    if n_trades > 0:
        print(f"  {product:<22s}  {n_trades:>5d} trades  {tot_vol:>6d} units")

print()
# Moves majeurs : top 5 plus gros mouvements de mid (> 5 ticks en < 1000 ts)
print("=" * 100)
print("MOUVEMENTS RAPIDES (>5 ticks en <1000 ts) — opportunités timing :")
print("=" * 100)
for product in ["HYDROGEL_PACK", "VELVETFRUIT_EXTRACT"]:
    pdata = sorted(products_data.get(product, []))
    moves = []
    for i in range(1, len(pdata)):
        if pdata[i][0] - pdata[i-1][0] <= 1000:
            dm = pdata[i][1] - pdata[i-1][1]
            if abs(dm) >= 3:
                moves.append((pdata[i-1][0], pdata[i][0], pdata[i-1][1], pdata[i][1], dm))
    moves.sort(key=lambda x: -abs(x[4]))
    print(f"\n  {product} top 5 moves :")
    for ts1, ts2, m1, m2, dm in moves[:5]:
        print(f"    ts {ts1:>6d}→{ts2:>6d}  mid {m1:.1f}→{m2:.1f}  Δ={dm:+.1f}")
