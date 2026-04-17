"""
Analyse profonde des logs IMC existants (276310, 278158, 278419).
Extrait :
  1. Distribution des fills SUBMISSION par edge vs FV
  2. Stats du book (spread, depth, dépendance prix/volume)
  3. Pattern temporels des trades (clusters, spikes)
  4. Différences v31 run1 vs v31 run2 (vraie variance)
  5. Effet id_markout v3a (différence réelle vs v31 moyen)
"""
import json
import re
import os
from collections import defaultdict, Counter

LOGS = {
    "276310_v31_run1": "/Users/danyballand/Downloads/276310/276310.log",
    "278419_v31_run2": "/Users/danyballand/Downloads/278419/278419.log",
    "278158_v3a":      "/Users/danyballand/Downloads/278158/278158.log",
}


def parse_log(path):
    """Parse IMC log json, extract activitiesLog + sandboxLogs + trades."""
    with open(path) as f:
        data = f.read()

    # activitiesLog contains tick-by-tick book snapshots + PnL
    m = re.search(r'"activitiesLog":"([^"]+)"', data)
    activities = m.group(1).replace('\\n', '\n') if m else ""

    # trades array (after activitiesLog)
    m2 = re.search(r'"trades":(\[[^\]]+\])', data)
    trades_raw = m2.group(1) if m2 else "[]"
    try:
        trades = json.loads(trades_raw)
    except:
        trades = []

    return activities, trades


def analyze_submission_fills(trades):
    """Fills où SUBMISSION est buyer or seller."""
    stats = {"Osm": {"buy_prices": [], "sell_prices": [], "buy_qty": [], "sell_qty": []},
             "Pep": {"buy_prices": [], "sell_prices": [], "buy_qty": [], "sell_qty": []}}
    for tr in trades:
        sym = "Osm" if tr["symbol"] == "ASH_COATED_OSMIUM" else "Pep"
        if tr["buyer"] == "SUBMISSION":
            stats[sym]["buy_prices"].append(tr["price"])
            stats[sym]["buy_qty"].append(tr["quantity"])
        elif tr["seller"] == "SUBMISSION":
            stats[sym]["sell_prices"].append(tr["price"])
            stats[sym]["sell_qty"].append(tr["quantity"])
    return stats


def book_snapshots(activities, product):
    """Returns list of (ts, bb, ba, bv1, av1, spread) for product."""
    rows = []
    for line in activities.strip().split('\n'):
        parts = line.split(';')
        if len(parts) < 17 or parts[0] == 'day': continue
        if parts[2] != product: continue
        ts = int(parts[1])
        try:
            bb = int(parts[3]) if parts[3] else None
            bv1 = int(parts[4]) if parts[4] else 0
            ba = int(parts[9]) if parts[9] else None
            av1 = int(parts[10]) if parts[10] else 0
        except (ValueError, IndexError):
            continue
        if bb is None or ba is None: continue
        spread = ba - bb
        mid = (bb + ba) / 2
        try: pnl = float(parts[-1])
        except: pnl = 0
        rows.append({"ts": ts, "bb": bb, "ba": ba, "bv1": bv1, "av1": av1,
                     "spread": spread, "mid": mid, "pnl": pnl})
    return rows


# === Main analysis ===

print("=" * 90)
print("ANALYSE PROFONDE DES 3 LOGS IMC")
print("=" * 90)

all_stats = {}
for label, path in LOGS.items():
    if not os.path.exists(path):
        print(f"SKIP {label}: file not found")
        continue
    activities, trades = parse_log(path)
    sub_fills = analyze_submission_fills(trades)
    pep_book = book_snapshots(activities, "INTARIAN_PEPPER_ROOT")
    osm_book = book_snapshots(activities, "ASH_COATED_OSMIUM")

    all_stats[label] = {"sub_fills": sub_fills, "pep_book": pep_book, "osm_book": osm_book,
                        "total_trades": len(trades)}

# === 1. Fills SUBMISSION comparison ===
print("\n### 1. FILLS SUBMISSION (BUY/SELL par produit)")
print(f"{'Run':<25} {'Osm buys':>10} {'Osm sells':>10} {'Pep buys':>10} {'Pep sells':>10}")
for lbl, s in all_stats.items():
    f = s["sub_fills"]
    print(f"{lbl:<25} {len(f['Osm']['buy_prices']):>10} {len(f['Osm']['sell_prices']):>10} {len(f['Pep']['buy_prices']):>10} {len(f['Pep']['sell_prices']):>10}")

# === 2. Distribution des prix des fills Osm par edge ===
print("\n### 2. DISTRIBUTION PRIX FILLS OSMIUM (edge vs fv=10000)")
for lbl, s in all_stats.items():
    print(f"\n-- {lbl} --")
    f = s["sub_fills"]["Osm"]
    # BUY: edge = 10000 - price (négatif = buy above fv = adverse)
    buy_edges = [10000 - p for p in f["buy_prices"]]
    sell_edges = [p - 10000 for p in f["sell_prices"]]
    if buy_edges:
        bc = Counter(buy_edges)
        print(f"  BUY edges (fv-price), total {sum(bc.values())} fills:")
        for e in sorted(bc.keys()):
            mark = "✓" if e > 0 else "✗"
            print(f"    edge={e:+3d}: n={bc[e]:>3} {mark}")
    if sell_edges:
        sc = Counter(sell_edges)
        print(f"  SELL edges (price-fv), total {sum(sc.values())} fills:")
        for e in sorted(sc.keys()):
            mark = "✓" if e > 0 else "✗"
            print(f"    edge={e:+3d}: n={sc[e]:>3} {mark}")

# === 3. Stats book ===
print("\n### 3. STATS BOOK (spread + depth L1) par run")
print(f"{'Run':<25} {'Pep spread':>12} {'Pep L1_bid_vol':>15} {'Pep L1_ask_vol':>15} {'Osm spread':>12}")
for lbl, s in all_stats.items():
    if not s["pep_book"]: continue
    pep_spreads = [r["spread"] for r in s["pep_book"]]
    pep_bv1 = [r["bv1"] for r in s["pep_book"]]
    pep_av1 = [r["av1"] for r in s["pep_book"]]
    osm_spreads = [r["spread"] for r in s["osm_book"]]
    print(f"{lbl:<25} {sum(pep_spreads)/len(pep_spreads):>12.2f} {sum(pep_bv1)/len(pep_bv1):>15.2f} {sum(pep_av1)/len(pep_av1):>15.2f} {sum(osm_spreads)/len(osm_spreads):>12.2f}")

# === 4. PnL progression comparison ===
print("\n### 4. PnL PROGRESSION (sample ts)")
print(f"{'Run':<25} {'ts':>7} {'Osm_pnl':>10} {'Pep_pnl':>10} {'Total':>10}")
for lbl, s in all_stats.items():
    if not s["pep_book"] or not s["osm_book"]: continue
    osm_by_ts = {r["ts"]: r["pnl"] for r in s["osm_book"]}
    pep_by_ts = {r["ts"]: r["pnl"] for r in s["pep_book"]}
    for ts in [10000, 30000, 50000, 70000, 90000, 99900]:
        op = osm_by_ts.get(ts, 0); pp = pep_by_ts.get(ts, 0)
        print(f"{lbl:<25} {ts:>7} {op:>+10.1f} {pp:>+10.1f} {op+pp:>+10.1f}")
    print()

# === 5. Comparaison run1 vs run2 (v31 pur) vs v3a ===
print("\n### 5. VARIANCE v31 vs EFFET v3a")
r1 = all_stats.get("276310_v31_run1")
r2 = all_stats.get("278419_v31_run2")
r3 = all_stats.get("278158_v3a")
if r1 and r2 and r3:
    # Osm fills counts
    r1_osm = len(r1["sub_fills"]["Osm"]["buy_prices"]) + len(r1["sub_fills"]["Osm"]["sell_prices"])
    r2_osm = len(r2["sub_fills"]["Osm"]["buy_prices"]) + len(r2["sub_fills"]["Osm"]["sell_prices"])
    r3_osm = len(r3["sub_fills"]["Osm"]["buy_prices"]) + len(r3["sub_fills"]["Osm"]["sell_prices"])
    print(f"Osm total fills: v31_r1={r1_osm}  v31_r2={r2_osm}  v3a={r3_osm}")
    print(f"  variance v31: {abs(r1_osm - r2_osm)} fills diff")
    print(f"  delta v3a vs v31 moyen: {r3_osm - (r1_osm+r2_osm)/2:+.1f} fills")

    # PnL final
    r1_final = r1["osm_book"][-1]["pnl"] + r1["pep_book"][-1]["pnl"] if r1["osm_book"] else 0
    r2_final = r2["osm_book"][-1]["pnl"] + r2["pep_book"][-1]["pnl"] if r2["osm_book"] else 0
    r3_final = r3["osm_book"][-1]["pnl"] + r3["pep_book"][-1]["pnl"] if r3["osm_book"] else 0
    print(f"\nPnL final: v31_r1={r1_final:.0f}  v31_r2={r2_final:.0f}  v3a={r3_final:.0f}")
    print(f"  variance v31: {abs(r1_final - r2_final):.0f}")
    print(f"  delta v3a vs v31 moyen: {r3_final - (r1_final+r2_final)/2:+.0f}")
