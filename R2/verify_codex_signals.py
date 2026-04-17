"""
Vérifie les 2 signaux Codex sur les CSV R2 :
  1. Pepper : snap-back trend-residual (trend = anchor + 0.001*ts)
  2. Osmium : next-move model E[mid_{t+1} - mid_t] = 4.6*OBI - 0.028*(mid - 10000)

Piège data noté par Codex : mid_price=0 sur one-sided snapshots → filter.
"""
import csv
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
DAYS = [-1, 0, 1]


def load_day(day):
    """Load prices CSV, compute clean mid (None if one-sided), OBI."""
    path = os.path.join(DATA_DIR, f"prices_round_2_day_{day}.csv")
    data = defaultdict(list)  # product -> list of (ts, mid, obi, total_bid, total_ask, bb, ba)
    with open(path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            ts = int(row["timestamp"])
            p = row["product"]
            bids = []; asks = []
            for i in (1, 2, 3):
                bp = row.get(f"bid_price_{i}", ""); bv = row.get(f"bid_volume_{i}", "")
                ap = row.get(f"ask_price_{i}", ""); av = row.get(f"ask_volume_{i}", "")
                if bp and bv: bids.append((int(bp), int(bv)))
                if ap and av: asks.append((int(ap), int(av)))
            if not bids or not asks:
                mid = None
            else:
                bb = max(b[0] for b in bids); ba = min(a[0] for a in asks)
                mid = (bb + ba) / 2.0
            total_b = sum(b[1] for b in bids); total_a = sum(a[1] for a in asks)
            obi = (total_b - total_a) / (total_b + total_a) if (total_b + total_a) > 0 else 0
            bb = max(b[0] for b in bids) if bids else None
            ba = min(a[0] for a in asks) if asks else None
            data[p].append((ts, mid, obi, total_b, total_a, bb, ba))
    return data


print("=" * 80)
print("VÉRIFICATION SIGNAUX CODEX")
print("=" * 80)

# === STAT 1 : Pepper trend linéaire 0.001/tick
print("\n### 1. PEPPER : trend linéaire + snap-back residual")
for day in DAYS:
    d = load_day(day)
    pep = [(ts, mid) for ts, mid, _, _, _, _, _ in d["INTARIAN_PEPPER_ROOT"] if mid is not None]
    if not pep: continue
    n = len(pep)
    # anchor = mid initial
    anchor = pep[0][1]
    mean_mid = sum(m for _, m in pep) / n
    # Fit slope via least squares
    xs = [ts for ts, _ in pep]; ys = [m for _, m in pep]
    xm = sum(xs)/n; ym = sum(ys)/n
    slope = sum((x-xm)*(y-ym) for x,y in zip(xs,ys)) / sum((x-xm)**2 for x in xs)
    print(f"  day {day:+d}: anchor={anchor:.1f}  mean_mid={mean_mid:.1f}  fitted_slope={slope:.6f}/tick  (Codex claim: ~0.001)")

# === STAT 2 : Pepper snap-back trades ex-ante
print("\n### 2. PEPPER : snap-back ex-ante trades (entrée au touch, sortie snapshot suivant)")
for thresh in [3, 4, 5, 6]:
    total_n = 0; total_sum = 0
    for day in DAYS:
        d = load_day(day)
        pep = [(ts, mid, bb, ba) for ts, mid, obi, tb, ta, bb, ba in d["INTARIAN_PEPPER_ROOT"] if mid is not None]
        if not pep: continue
        anchor = pep[0][1]
        slope = 0.001
        trades_pnl = []
        for i in range(len(pep) - 1):
            ts, mid, bb, ba = pep[i]
            next_mid = pep[i+1][1]
            trend = anchor + slope * ts
            resid = mid - trend
            if resid <= -thresh and ba is not None:
                # BUY at ask, sell at next mid
                pnl = next_mid - ba
                trades_pnl.append(pnl)
            elif resid >= thresh and bb is not None:
                # SELL at bid, buy back at next mid
                pnl = bb - next_mid
                trades_pnl.append(pnl)
        if trades_pnl:
            total_n += len(trades_pnl)
            total_sum += sum(trades_pnl)
    if total_n > 0:
        mean = total_sum / total_n
        print(f"  threshold={thresh}: n={total_n}  total={total_sum:+.1f} ticks  mean={mean:+.2f}/trade  (Codex seuil 5: n=639 mean+3.73)")

# === STAT 3 : Osmium next-move model
print("\n### 3. OSMIUM : E[mid_{t+1} - mid_t] = a*OBI + b*(mid - 10000)")
for day in DAYS:
    d = load_day(day)
    osm = [(ts, mid, obi) for ts, mid, obi, _, _, _, _ in d["ASH_COATED_OSMIUM"] if mid is not None]
    # Build pairs (OBI_t, mid_t - 10000, mid_{t+1} - mid_t)
    pairs = []
    for i in range(len(osm) - 1):
        ts, mid, obi = osm[i]
        next_mid = osm[i+1][1]
        pairs.append((obi, mid - 10000, next_mid - mid))
    if not pairs: continue
    # Fit: y = a*x1 + b*x2 via normal equations
    n = len(pairs)
    sx1 = sum(p[0] for p in pairs); sx2 = sum(p[1] for p in pairs); sy = sum(p[2] for p in pairs)
    sx1x1 = sum(p[0]**2 for p in pairs); sx2x2 = sum(p[1]**2 for p in pairs)
    sx1x2 = sum(p[0]*p[1] for p in pairs); sx1y = sum(p[0]*p[2] for p in pairs)
    sx2y = sum(p[1]*p[2] for p in pairs)
    # (without intercept for simplicity, centered around 10000)
    # Solve 2x2 system : [sx1x1 sx1x2] [a]   [sx1y]
    #                    [sx1x2 sx2x2] [b] = [sx2y]
    det = sx1x1 * sx2x2 - sx1x2 * sx1x2
    if abs(det) > 1e-9:
        a = (sx1y * sx2x2 - sx2y * sx1x2) / det
        b = (sx1x1 * sx2y - sx1x2 * sx1y) / det
        # R² = 1 - SSR/SST
        sst = sum((p[2])**2 for p in pairs)
        ssr = sum((p[2] - a*p[0] - b*p[1])**2 for p in pairs)
        r2 = 1 - ssr/sst if sst > 0 else 0
        print(f"  day {day:+d}: a(OBI)={a:+.3f}  b(MR)={b:+.4f}  R²={r2:.4f}  n={n}  (Codex: a~4.6  b~-0.03)")

# === STAT 4 : Trade-flow asymmetry Pepper
print("\n### 4. PEPPER : trade-flow asymmetry (hits ask vs bid selon resid)")
for day in DAYS:
    trades_path = os.path.join(DATA_DIR, f"trades_round_2_day_{day}.csv")
    if not os.path.exists(trades_path): continue
    d = load_day(day)
    pep_books = {ts: (mid, bb, ba) for ts, mid, obi, _, _, bb, ba in d["INTARIAN_PEPPER_ROOT"] if mid is not None}
    anchor = d["INTARIAN_PEPPER_ROOT"][0][1] if d["INTARIAN_PEPPER_ROOT"] else 0
    slope = 0.001
    ask_hits_neg = 0; bid_hits_neg = 0
    ask_hits_pos = 0; bid_hits_pos = 0
    with open(trades_path) as f:
        for row in csv.DictReader(f, delimiter=";"):
            if row["symbol"] != "INTARIAN_PEPPER_ROOT": continue
            ts = int(row["timestamp"])
            if ts not in pep_books: continue
            mid, bb, ba = pep_books[ts]
            if mid is None: continue
            price = float(row["price"])
            trend = anchor + slope * ts
            resid = mid - trend
            # classify: price near ask = market buy, price near bid = market sell
            is_buy_agg = ba is not None and price >= ba
            is_sell_agg = bb is not None and price <= bb
            if resid <= -5:
                if is_buy_agg: ask_hits_neg += 1
                if is_sell_agg: bid_hits_neg += 1
            elif resid >= 5:
                if is_buy_agg: ask_hits_pos += 1
                if is_sell_agg: bid_hits_pos += 1
    total_neg = ask_hits_neg + bid_hits_neg
    total_pos = ask_hits_pos + bid_hits_pos
    if total_neg > 0:
        print(f"  day {day:+d} resid<=-5: ask_hits={ask_hits_neg} ({100*ask_hits_neg/total_neg:.1f}%)  bid_hits={bid_hits_neg} ({100*bid_hits_neg/total_neg:.1f}%)  n={total_neg}")
    if total_pos > 0:
        print(f"  day {day:+d} resid>=+5: bid_hits={bid_hits_pos} ({100*bid_hits_pos/total_pos:.1f}%)  ask_hits={ask_hits_pos} ({100*ask_hits_pos/total_pos:.1f}%)  n={total_pos}")

print("\n" + "=" * 80)
print("VERDICT : si les chiffres matchent Codex → signaux validés → on code v4")
print("=" * 80)
