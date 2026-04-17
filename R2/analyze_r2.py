"""
analyze_r2.py — Analyse 1-click des CSV R2 dès leur release.

Usage :
    python3 analyze_r2.py ROUND_2/
ou :
    python3 analyze_r2.py /path/to/prices_round_2_day_X.csv

Ce script produit en < 30 sec :
  1. Stats par produit (mean, std, range, drift)
  2. Matrice de corrélation des mids
  3. OLS régression pairs/triples (détection cointégration)
  4. Engle-Granger ADF test sur spreads candidats
  5. Half-life Ornstein-Uhlenbeck (mean-reversion speed)
  6. Détection de basket (combinaisons linéaires) via OLS multi-input
  7. Volumétrie des books (spreads, depths, volumes)
  8. Comportement bot (si trades CSV disponible)

Output : rapport markdown + CSV de corrélations.
"""
import csv
import os
import sys
import glob
import math
from collections import defaultdict
from itertools import combinations


# ============================================================================
# LOADING
# ============================================================================

def load_prices(path, max_ts=100_000):
    """Retourne {ts: {product: {'bid1','ask1','mid','bid_vol1','ask_vol1',...}}}"""
    snapshots = defaultdict(dict)
    with open(path) as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ts = int(row["timestamp"])
            if ts >= max_ts:
                continue
            p = row["product"]
            d = {}
            for i in (1, 2, 3):
                for side in ("bid", "ask"):
                    for kind in ("price", "volume"):
                        k = f"{side}_{kind}_{i}"
                        v = row.get(k, "")
                        if v not in ("", None):
                            d[k] = int(float(v))
            # compute mid from best bid/ask
            bb = d.get("bid_price_1")
            ba = d.get("ask_price_1")
            if bb is not None and ba is not None:
                d["mid"] = (bb + ba) / 2.0
                d["spread"] = ba - bb
            elif bb is not None:
                d["mid"] = float(bb); d["spread"] = None
            elif ba is not None:
                d["mid"] = float(ba); d["spread"] = None
            snapshots[ts][p] = d
    return snapshots


def load_trades(path, max_ts=100_000):
    """Retourne {ts: {product: [trades]}}"""
    trades = defaultdict(lambda: defaultdict(list))
    if not os.path.exists(path):
        return trades
    with open(path) as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ts = int(row["timestamp"])
            if ts >= max_ts:
                continue
            prod = row.get("symbol") or row.get("product", "")
            trades[ts][prod].append({
                "price": float(row["price"]),
                "qty": int(row["quantity"]),
                "buyer": row.get("buyer", ""),
                "seller": row.get("seller", ""),
            })
    return trades


# ============================================================================
# STATS
# ============================================================================

def basic_stats(mids_series):
    """mean, std, min, max, drift (mid[-1] - mid[0])"""
    if not mids_series:
        return None
    n = len(mids_series)
    mean = sum(mids_series) / n
    var = sum((x - mean) ** 2 for x in mids_series) / max(1, n - 1)
    std = var ** 0.5
    return {
        "n": n,
        "mean": mean,
        "std": std,
        "min": min(mids_series),
        "max": max(mids_series),
        "drift": mids_series[-1] - mids_series[0],
        "range": max(mids_series) - min(mids_series),
    }


def correlation(x, y):
    """Pearson correlation."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    dx = sum((x[i] - mx) ** 2 for i in range(n)) ** 0.5
    dy = sum((y[i] - my) ** 2 for i in range(n)) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def ols_simple(x, y):
    """y = a + b*x. Returns (a, b, r2)."""
    n = min(len(x), len(y))
    if n < 3:
        return None
    mx = sum(x[:n]) / n
    my = sum(y[:n]) / n
    num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    den = sum((x[i] - mx) ** 2 for i in range(n))
    if den == 0:
        return None
    b = num / den
    a = my - b * mx
    # r^2
    ss_tot = sum((y[i] - my) ** 2 for i in range(n))
    ss_res = sum((y[i] - a - b * x[i]) ** 2 for i in range(n))
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {"a": a, "b": b, "r2": r2, "n": n}


def ols_multi(X_cols, y):
    """
    Multiple OLS : y = a + b1*x1 + b2*x2 + ... via normal equations (no numpy).
    X_cols = list of lists (chacun une colonne).
    Returns {'intercept': a, 'coeffs': [b1, b2, ...], 'r2': float, 'residuals': [...]}
    """
    k = len(X_cols)
    n = min(len(y), min(len(c) for c in X_cols))
    if n < k + 2:
        return None
    # X design: n rows, k+1 cols (1, x1, x2, ...)
    # Normal equations : (X^T X) beta = X^T y
    # Solve manually for k <= 4 via Gauss elimination
    XtX = [[0.0] * (k + 1) for _ in range(k + 1)]
    Xty = [0.0] * (k + 1)
    for i in range(n):
        row = [1.0] + [X_cols[j][i] for j in range(k)]
        for r in range(k + 1):
            for c in range(k + 1):
                XtX[r][c] += row[r] * row[c]
            Xty[r] += row[r] * y[i]
    # augmented matrix
    A = [XtX[r] + [Xty[r]] for r in range(k + 1)]
    # Gaussian elimination
    for col in range(k + 1):
        # pivot
        piv = col
        for r in range(col + 1, k + 1):
            if abs(A[r][col]) > abs(A[piv][col]):
                piv = r
        A[col], A[piv] = A[piv], A[col]
        if abs(A[col][col]) < 1e-12:
            return None
        for r in range(k + 1):
            if r == col:
                continue
            factor = A[r][col] / A[col][col]
            for c in range(col, k + 2):
                A[r][c] -= factor * A[col][c]
    beta = [A[r][k + 1] / A[r][r] for r in range(k + 1)]
    intercept = beta[0]
    coeffs = beta[1:]
    # r2
    my = sum(y[:n]) / n
    ss_tot = sum((y[i] - my) ** 2 for i in range(n))
    residuals = [y[i] - intercept - sum(coeffs[j] * X_cols[j][i] for j in range(k)) for i in range(n)]
    ss_res = sum(r * r for r in residuals)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {"intercept": intercept, "coeffs": coeffs, "r2": r2, "residuals": residuals, "n": n}


def adf_simple(series):
    """
    Simplified Augmented Dickey-Fuller : regression Δy_t = α y_{t-1} + β + ε
    Stationary si α significatif < 0 (approx via t-stat).
    Returns {'alpha', 'tstat', 'is_stationary_approx'}
    """
    n = len(series)
    if n < 20:
        return None
    y_lag = series[:-1]
    dy = [series[i] - series[i - 1] for i in range(1, n)]
    res = ols_simple(y_lag, dy)
    if res is None:
        return None
    alpha = res["b"]
    # t-stat rough : need SE(alpha)
    my = sum(dy) / len(dy)
    mx = sum(y_lag) / len(y_lag)
    ss_xx = sum((y_lag[i] - mx) ** 2 for i in range(len(y_lag)))
    ss_res = sum((dy[i] - res["a"] - alpha * y_lag[i]) ** 2 for i in range(len(y_lag)))
    sigma2 = ss_res / max(1, len(y_lag) - 2)
    se_alpha = (sigma2 / ss_xx) ** 0.5 if ss_xx > 0 else float("inf")
    tstat = alpha / se_alpha if se_alpha > 0 else 0.0
    # ADF 5% critical ~ -2.86 for n>100. We use a looser proxy.
    is_stationary = tstat < -2.5
    return {"alpha": alpha, "tstat": tstat, "is_stationary_approx": is_stationary}


def half_life_ou(series):
    """
    Half-life of mean reversion via OU : Δy = -λ(y - μ) dt
    Regression Δy_t on y_{t-1}, λ = -β, half-life = ln(2)/λ.
    """
    n = len(series)
    if n < 20:
        return None
    y_lag = series[:-1]
    dy = [series[i] - series[i - 1] for i in range(1, n)]
    res = ols_simple(y_lag, dy)
    if res is None or res["b"] >= 0:
        return None  # not mean-reverting
    lam = -res["b"]
    if lam <= 0:
        return None
    hl = math.log(2) / lam
    return {"lambda": lam, "half_life_ticks": hl}


# ============================================================================
# DETECTION
# ============================================================================

def detect_pairs(mids_by_product, min_corr=0.85):
    """Trouve paires (a, b) avec |corr| > threshold."""
    products = sorted(mids_by_product.keys())
    # align on common timestamps
    pairs_found = []
    for a, b in combinations(products, 2):
        xs, ys = mids_by_product[a], mids_by_product[b]
        n = min(len(xs), len(ys))
        if n < 50:
            continue
        c = correlation(xs[:n], ys[:n])
        if abs(c) < min_corr:
            continue
        ols = ols_simple(xs[:n], ys[:n])
        if ols is None:
            continue
        # spread = y - (a + b*x)
        spread = [ys[i] - ols["a"] - ols["b"] * xs[i] for i in range(n)]
        adf = adf_simple(spread)
        hl = half_life_ou(spread)
        pairs_found.append({
            "a": a, "b": b, "corr": c, "ols": ols,
            "spread_mean": sum(spread) / n,
            "spread_std": (sum((s - sum(spread) / n) ** 2 for s in spread) / max(1, n - 1)) ** 0.5,
            "adf": adf, "half_life": hl,
        })
    pairs_found.sort(key=lambda x: -abs(x["corr"]))
    return pairs_found


def detect_basket(mids_by_product, target_product, other_products, min_r2=0.90):
    """
    Teste si target = a + b1*x1 + b2*x2 + ... (basket formula).
    Returns OLS multi si r2 > threshold.
    """
    n = min([len(mids_by_product[target_product])] +
            [len(mids_by_product[p]) for p in other_products])
    if n < 50:
        return None
    y = mids_by_product[target_product][:n]
    X_cols = [mids_by_product[p][:n] for p in other_products]
    res = ols_multi(X_cols, y)
    if res is None:
        return None
    if res["r2"] < min_r2:
        return None
    # spread = residuals ; check mean-reversion
    adf = adf_simple(res["residuals"])
    hl = half_life_ou(res["residuals"])
    return {"target": target_product, "components": other_products,
            "intercept": res["intercept"], "coeffs": res["coeffs"],
            "r2": res["r2"], "adf": adf, "half_life": hl,
            "spread_std": (sum((r - sum(res["residuals"]) / len(res["residuals"])) ** 2
                              for r in res["residuals"]) / max(1, len(res["residuals"]) - 1)) ** 0.5}


def round_coeff_candidates(coeff, max_int=10):
    """Pour une OLS coeff, cherche le(s) entier(s) ou demi-entiers proches."""
    candidates = []
    for target in range(1, max_int + 1):
        if abs(coeff - target) < 0.3:
            candidates.append(target)
    return candidates or [round(coeff, 2)]


# ============================================================================
# REPORTING
# ============================================================================

def fmt_num(x, w=10, d=2):
    if x is None:
        return "       --"
    return f"{x:>{w}.{d}f}"


def generate_report(snapshots, trades, out_path):
    products = sorted({p for s in snapshots.values() for p in s.keys()})
    timestamps = sorted(snapshots.keys())

    # Build aligned mid series per product (fill forward missing)
    mids_by_product = {p: [] for p in products}
    last_seen = {p: None for p in products}
    for ts in timestamps:
        for p in products:
            d = snapshots[ts].get(p)
            if d is not None and "mid" in d:
                last_seen[p] = d["mid"]
            if last_seen[p] is not None:
                mids_by_product[p].append(last_seen[p])

    lines = []
    lines.append("# R2 ANALYSIS REPORT\n")
    lines.append(f"- Products: {products}")
    lines.append(f"- Ticks: {len(timestamps)}")
    lines.append(f"- File: {out_path}\n")

    # === 1. Basic stats ===
    lines.append("## 1. Basic stats per product\n")
    lines.append(f"{'product':<30} {'n':>6} {'mean':>12} {'std':>10} {'min':>10} {'max':>10} {'drift':>10} {'range':>10}")
    lines.append("-" * 110)
    for p in products:
        s = basic_stats(mids_by_product[p])
        if s is None: continue
        lines.append(f"{p:<30} {s['n']:>6} {s['mean']:>12.2f} {s['std']:>10.2f} "
                     f"{s['min']:>10.2f} {s['max']:>10.2f} {s['drift']:>+10.2f} {s['range']:>10.2f}")

    # === 2. Spreads + depth ===
    lines.append("\n## 2. Order book characteristics\n")
    lines.append(f"{'product':<30} {'avg_spread':>12} {'avg_depth_bid':>15} {'avg_depth_ask':>15}")
    lines.append("-" * 80)
    for p in products:
        spreads = []
        d_bid, d_ask = [], []
        for ts in timestamps:
            d = snapshots[ts].get(p, {})
            if d.get("spread") is not None:
                spreads.append(d["spread"])
            for i in (1, 2, 3):
                bv = d.get(f"bid_volume_{i}")
                av = d.get(f"ask_volume_{i}")
                if bv: d_bid.append(bv)
                if av: d_ask.append(av)
        avg_sp = sum(spreads) / len(spreads) if spreads else None
        avg_db = sum(d_bid) / len(d_bid) if d_bid else None
        avg_da = sum(d_ask) / len(d_ask) if d_ask else None
        lines.append(f"{p:<30} {fmt_num(avg_sp,12)} {fmt_num(avg_db,15)} {fmt_num(avg_da,15)}")

    # === 3. Correlation matrix ===
    lines.append("\n## 3. Correlation matrix (mids)\n")
    header = f"{'':<30}" + "".join(f"{p[:12]:>14}" for p in products)
    lines.append(header)
    for p1 in products:
        row = f"{p1:<30}"
        for p2 in products:
            n = min(len(mids_by_product[p1]), len(mids_by_product[p2]))
            c = correlation(mids_by_product[p1][:n], mids_by_product[p2][:n])
            row += f"{c:>+14.3f}"
        lines.append(row)

    # === 4. Pair cointegration ===
    lines.append("\n## 4. Pair cointegration candidates (|corr| > 0.85)\n")
    pairs = detect_pairs(mids_by_product, min_corr=0.85)
    if not pairs:
        lines.append("*No strong pairs found.*")
    else:
        lines.append(f"{'A':<22} {'B':<22} {'corr':>6} {'b':>8} {'a':>10} {'r2':>6} {'half_life':>10} {'ADF_t':>8} {'stat?':>6}")
        lines.append("-" * 110)
        for p in pairs[:20]:
            hl = p["half_life"]["half_life_ticks"] if p["half_life"] else None
            adf_t = p["adf"]["tstat"] if p["adf"] else None
            stat = "YES" if (p["adf"] and p["adf"]["is_stationary_approx"]) else "no"
            lines.append(f"{p['a']:<22} {p['b']:<22} {p['corr']:>+6.3f} "
                         f"{p['ols']['b']:>+8.3f} {p['ols']['a']:>+10.2f} "
                         f"{p['ols']['r2']:>6.3f} {fmt_num(hl,10,1)} "
                         f"{fmt_num(adf_t,8,2)} {stat:>6}")

    # === 5. Basket detection ===
    # Pour chaque produit avec forte corr avec >=2 autres, tente basket fit
    lines.append("\n## 5. Basket detection (y = a + Σ bi·xi, r² ≥ 0.90)\n")
    baskets = []
    for target in products:
        others = [p for p in products if p != target]
        if len(others) < 2:
            continue
        # Essaie combinations de 2 et 3 composants
        for k in (2, 3, 4):
            if len(others) < k:
                continue
            for combo in combinations(others, k):
                b = detect_basket(mids_by_product, target, list(combo), min_r2=0.90)
                if b:
                    baskets.append(b)
    baskets.sort(key=lambda x: -x["r2"])
    if not baskets:
        lines.append("*No basket relation r² ≥ 0.90 found.*")
    else:
        for b in baskets[:10]:
            comps = " + ".join(f"{b['coeffs'][i]:+.3f}·{b['components'][i]}" for i in range(len(b['components'])))
            hl = b["half_life"]["half_life_ticks"] if b["half_life"] else None
            adf_t = b["adf"]["tstat"] if b["adf"] else None
            lines.append(f"\n- **{b['target']}** = {b['intercept']:+.2f} {comps}")
            lines.append(f"  r²={b['r2']:.4f}  spread_std={b['spread_std']:.2f}  "
                         f"half_life={fmt_num(hl, 6, 1)}  ADF_t={fmt_num(adf_t, 6, 2)}")
            # integer-weight suggestions
            int_candidates = []
            for i, c in enumerate(b['coeffs']):
                ints = round_coeff_candidates(c)
                int_candidates.append(f"{b['components'][i]}={ints}")
            lines.append(f"  integer-weight candidates: {', '.join(int_candidates)}")

    # === 6. Bot autopsy (si trades dispo) ===
    lines.append("\n## 6. Bot / trade flow\n")
    if not trades:
        lines.append("*No trades CSV found.*")
    else:
        for p in products:
            bot_counter = defaultdict(lambda: {"n": 0, "vol": 0, "buys": 0, "sells": 0})
            total_n = 0
            for ts, by_prod in trades.items():
                for tr in by_prod.get(p, []):
                    total_n += 1
                    if tr["buyer"]:
                        bot_counter[tr["buyer"]]["buys"] += tr["qty"]
                        bot_counter[tr["buyer"]]["n"] += 1
                        bot_counter[tr["buyer"]]["vol"] += tr["qty"]
                    if tr["seller"]:
                        bot_counter[tr["seller"]]["sells"] += tr["qty"]
                        bot_counter[tr["seller"]]["n"] += 1
                        bot_counter[tr["seller"]]["vol"] += tr["qty"]
            if total_n == 0:
                continue
            lines.append(f"\n### {p} — {total_n} trades")
            top_bots = sorted(bot_counter.items(), key=lambda kv: -kv[1]["vol"])[:8]
            if top_bots:
                lines.append(f"  {'bot':<20} {'trades':>8} {'vol':>8} {'buys':>8} {'sells':>8} {'net':>8}")
                for name, s in top_bots:
                    net = s["buys"] - s["sells"]
                    lines.append(f"  {name:<20} {s['n']:>8} {s['vol']:>8} {s['buys']:>8} {s['sells']:>8} {net:>+8}")
            else:
                lines.append(f"  (bot IDs empty — backtest CSV)")

    # === 7. Quick interpretation ===
    lines.append("\n## 7. Quick interpretation\n")
    interp = []
    stable_products = []
    trending_products = []
    volatile_products = []
    for p in products:
        s = basic_stats(mids_by_product[p])
        if s is None: continue
        rel_std = s["std"] / abs(s["mean"]) if s["mean"] != 0 else 1.0
        drift_ratio = abs(s["drift"]) / s["range"] if s["range"] > 0 else 0  # 0..1
        if rel_std < 0.002:
            stable_products.append((p, s["mean"], s["std"]))
        elif drift_ratio > 0.4:
            trending_products.append((p, s["drift"], s["range"]))
        else:
            volatile_products.append((p, s["std"], s["range"]))
    if stable_products:
        interp.append("- **Stable products** (potential fixed-FV market making):")
        for p, m, s in stable_products:
            interp.append(f"  - {p}: fv≈{m:.2f}  std={s:.2f}")
    if trending_products:
        interp.append("- **Trending products** (potential directional play / bootstrap):")
        for p, d, r in trending_products:
            interp.append(f"  - {p}: drift {d:+.2f}  over range {r:.2f}  ({d/r*100:+.0f}% of range)")
    if volatile_products:
        interp.append("- **Volatile products** (neither clearly stable nor trending — spread-trade?):")
        for p, s, r in volatile_products:
            interp.append(f"  - {p}: std={s:.2f}  range={r:.2f}")
    if baskets:
        top = baskets[0]
        interp.append(f"- **Best basket found**: {top['target']} ≈ f({', '.join(top['components'])}) "
                      f"r²={top['r2']:.3f}")
        if top["half_life"]:
            interp.append(f"  half-life = {top['half_life']['half_life_ticks']:.1f} ticks "
                          f"({top['half_life']['half_life_ticks']/100:.1f} snapshots)")
    if pairs:
        strongest = pairs[0]
        interp.append(f"- **Strongest pair**: {strongest['a']} ↔ {strongest['b']} corr={strongest['corr']:+.3f}")
    lines.append("\n".join(interp) if interp else "*No immediate signal detected.*")

    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_r2.py <dir_or_csv>")
        sys.exit(1)
    arg = sys.argv[1]

    if os.path.isdir(arg):
        price_files = sorted(glob.glob(os.path.join(arg, "prices_round_*_day_*.csv")))
        trade_files = sorted(glob.glob(os.path.join(arg, "trades_round_*_day_*.csv")))
    elif os.path.isfile(arg):
        price_files = [arg]
        trade_files = []
    else:
        print(f"Not found: {arg}")
        sys.exit(1)

    if not price_files:
        print("No price CSV found.")
        sys.exit(1)

    print(f"Loading {len(price_files)} price files + {len(trade_files)} trade files...")
    # Combine all days into one giant timeline (offset per day)
    all_snapshots = {}
    all_trades = {}
    offset = 0
    for pf in price_files:
        snaps = load_prices(pf)
        for ts, d in snaps.items():
            all_snapshots[ts + offset] = d
        offset += 100_000
    offset = 0
    for tf in trade_files:
        trs = load_trades(tf)
        for ts, d in trs.items():
            all_trades[ts + offset] = d
        offset += 100_000

    print(f"Loaded {len(all_snapshots)} snapshots, {len(all_trades)} trade-ts")
    report = generate_report(all_snapshots, all_trades, arg)

    out_path = "R2_ANALYSIS_REPORT.md"
    with open(out_path, "w") as f:
        f.write(report)
    print(f"\nReport written to {out_path}")
    print("=" * 80)
    print(report)


if __name__ == "__main__":
    main()
