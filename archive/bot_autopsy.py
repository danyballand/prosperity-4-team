"""
Bot Autopsy — analyse offline des logs live IMC pour cartographier tous les bots.

USAGE :
  1. Upload un algo avec logger (v20 ci-dessous fait ça)
  2. Télécharge les logs (.log) de ta soumission
  3. python3 bot_autopsy.py /path/to/submission.log

Output : classement des bots par edge (markout), archétype, stratégie recommandée.
"""
import json
import re
import sys
from collections import defaultdict


def parse_log(logfile: str):
    """
    Parse un .log d'IMC. Format typique :
      - Ligne avec 'lambda' et data JSON (prints du trader)
      - Bloc d'activitiesLog CSV
      - Bloc de trades JSON
    On extrait les LINES commençant par 'BOT' ou 'IDMARK' ou 'OWNMO'.
    """
    with open(logfile) as f:
        content = f.read()

    # Recupère les prints du trader (lines avec notre format custom)
    bot_lines = re.findall(r"BOT ([^\n]+)", content)
    idmark_lines = re.findall(r"IDMARK ([^\n]+)", content)
    ownmo_lines = re.findall(r"OWNMO ([^\n]+)", content)
    return bot_lines, idmark_lines, ownmo_lines


def analyze_bots(bot_lines):
    """
    Attend un format : "BOT {product} {timestamp} buyer={id} seller={id} price={p} qty={q} fv={fv}"
    Construit des stats par ID.
    """
    stats = defaultdict(lambda: {
        "n_buys": 0, "n_sells": 0,
        "total_buy_vol": 0, "total_sell_vol": 0,
        "sizes": [],
        "buy_prices": [], "sell_prices": [],
        "timestamps": [],
        "markouts_100": [], "markouts_500": [], "markouts_1000": [],
    })

    # Collecte trades
    trades = []
    for line in bot_lines:
        parts = dict(x.split("=", 1) for x in line.split() if "=" in x)
        try:
            trades.append({
                "ts": int(parts.get("ts", parts.get("timestamp", "0"))),
                "product": parts.get("product", "?"),
                "buyer": parts.get("buyer", "").strip('"'),
                "seller": parts.get("seller", "").strip('"'),
                "price": float(parts.get("price", "0")),
                "qty": int(parts.get("qty", parts.get("quantity", "0"))),
                "fv": float(parts.get("fv", "0")),
            })
        except (ValueError, KeyError):
            continue

    if not trades:
        return {}

    # Markout : pour chaque trade, regarder fv à ts+100, +500, +1000
    trades.sort(key=lambda t: t["ts"])
    fv_by_ts = {t["ts"]: t["fv"] for t in trades if t["product"] == trades[0]["product"]}
    all_ts = sorted(fv_by_ts.keys())

    def fv_at(target_ts):
        # Approx : plus proche ts >= target
        for t in all_ts:
            if t >= target_ts:
                return fv_by_ts[t]
        return None

    for trade in trades:
        if trade["buyer"]:
            s = stats[trade["buyer"]]
            s["n_buys"] += 1
            s["total_buy_vol"] += trade["qty"]
            s["buy_prices"].append(trade["price"])
            s["sizes"].append(trade["qty"])
            s["timestamps"].append(trade["ts"])
            for h in (100, 500, 1000):
                fv_future = fv_at(trade["ts"] + h)
                if fv_future is not None:
                    mo = fv_future - trade["price"]  # markout pour un BUY
                    s[f"markouts_{h}"].append(mo)

        if trade["seller"]:
            s = stats[trade["seller"]]
            s["n_sells"] += 1
            s["total_sell_vol"] += trade["qty"]
            s["sell_prices"].append(trade["price"])
            s["sizes"].append(trade["qty"])
            s["timestamps"].append(trade["ts"])
            for h in (100, 500, 1000):
                fv_future = fv_at(trade["ts"] + h)
                if fv_future is not None:
                    mo = trade["price"] - fv_future  # markout pour un SELL
                    s[f"markouts_{h}"].append(mo)

    return stats


def classify_archetype(s):
    """Retourne l'archétype du bot selon ses stats."""
    n_buys = s["n_buys"]
    n_sells = s["n_sells"]
    n = n_buys + n_sells
    if n < 5:
        return "UNKNOWN (trop peu de data)"

    mo500 = s["markouts_500"]
    mean_mo = sum(mo500) / len(mo500) if mo500 else 0
    avg_size = sum(s["sizes"]) / len(s["sizes"]) if s["sizes"] else 0
    size_std = (sum((x - avg_size) ** 2 for x in s["sizes"]) / len(s["sizes"])) ** 0.5 if s["sizes"] else 0

    directional = abs(n_buys - n_sells) / n > 0.7

    if mean_mo > 2:
        return "🔥 INFORMED (markout positif consistant → COPIER)"
    if mean_mo < -1:
        return "❌ LOSER (markout négatif → FADER ou ignorer)"
    if not directional and abs(mean_mo) < 0.5:
        return "🏦 MARKET MAKER (neutre)"
    if directional and size_std / max(avg_size, 1) < 0.2:
        return "🤖 FIXED-SIZE BOT (taille constante → pattern détectable)"
    if avg_size > 30:
        return "🐋 WHALE (gros volume)"
    return "NOISE TRADER"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 bot_autopsy.py <logfile.log>")
        sys.exit(1)

    bot_lines, idmark_lines, ownmo_lines = parse_log(sys.argv[1])

    print(f"\n=== {len(bot_lines)} BOT events, {len(idmark_lines)} IDMARK, {len(ownmo_lines)} OWNMO ===\n")

    stats = analyze_bots(bot_lines)

    # Tri par volume total
    sorted_bots = sorted(stats.items(), key=lambda kv: kv[1]["n_buys"] + kv[1]["n_sells"], reverse=True)

    print(f"{'ID':<20} {'n_b':>4} {'n_s':>4} {'avg_size':>8} {'mo500_mean':>11} {'ARCHETYPE'}")
    print("-" * 100)
    for bot_id, s in sorted_bots[:30]:
        n_b, n_s = s["n_buys"], s["n_sells"]
        avg_size = sum(s["sizes"]) / len(s["sizes"]) if s["sizes"] else 0
        mo500 = s["markouts_500"]
        mo500_mean = sum(mo500) / len(mo500) if mo500 else 0
        archetype = classify_archetype(s)
        print(f"{bot_id:<20} {n_b:>4} {n_s:>4} {avg_size:>8.1f} {mo500_mean:>+11.2f}  {archetype}")


if __name__ == "__main__":
    main()
