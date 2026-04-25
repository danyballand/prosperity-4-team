"""
Génère versions audacieuses : patches qui peuvent ne pas marcher en backtest mais
qui ont une raison théorique solide en live.
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "trader_r3.py")

with open(BASE, "r") as f:
    src = f.read()


def write_version(name, transformations, header_comment):
    out = src
    for old, new in transformations:
        if old not in out:
            print(f'WARNING: {name} - old string not found: {old[:80]}')
            continue
        out = out.replace(old, new)
    out = f'"""\n=== {name} ===\n{header_comment}\n"""\n' + out
    path = os.path.join(HERE, f"trader_r3_{name}.py")
    with open(path, "w") as f:
        f.write(out)
    print(f'  Written: {path}')


# ============== SAFE BASELINE ==============
print('Generating v12_pure (baseline)...')
write_version(
    "v12_pure",
    [],
    "v12 PURE — match exact 401365/402921 = +22,776 confirmé."
)

# ============== AUDACIOUS PATCHES ==============

# v23 : 5400 SELL crossing (Codex finding, conditional → no downside)
print('Generating v23_5400_sell...')
write_version(
    "v23_5400_sell",
    [
        ('_VEV_DISABLED = {5200, 5300, 5400, 5500, 6000, 6500}',
         '_VEV_DISABLED = {5200, 5300, 5500, 6000, 6500}'),
        ('"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,',
         '"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,\n        "vev_5400_sell_overlay": (_strike == 5400),\n        "vev_5400_sell_size": 5,'),
    ],
    "v23 5400_SELL — v12 + Codex's only positive IV signal.\n"
    "Pattern : market_bid > smile_FV → SELL. Conditional, zero downside vs v12.\n"
    "Live attendu : +22,800 à +23,300 (capacity Codex +200 SS jour2)."
)

# v25 : LONG_LITE (HYD anti-bot-sell)
print('Generating v25_long_lite...')
write_version(
    "v25_long_lite",
    [
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_long_lite_enable": True,'),
    ],
    "v25 LONG_LITE — v12 + HYD anti-bot-sell pattern.\n"
    "Live obs 401365 : 4 trades anon AT_BID, mo10k mean +15.5. Filter seller=SUBMISSION.\n"
    "Live attendu : +22,500 à +24,000. Risque -1k si live ≠ pattern."
)

# v28 : BIG SIGNAL (trade qty >= 5 = bot très informé → SHORT 60)
print('Generating v28_big_signal...')
write_version(
    "v28_big_signal",
    [
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_big_signal": True,                  # v28 : qty>=5 → SHORT_BIG\n        "hyd_short_big_size": 60,'),
    ],
    "v28 BIG_SIGNAL — gros trade (qty>=5) = bot informé → SHORT 60 unités au lieu de 30.\n"
    "Hypothèse : la taille du trade signale la conviction du bot informé.\n"
    "Live attendu : +22,000 à +25,000. Risque -2k si signal noisy, gain +2k si fiable."
)

# v29 : POST-AVOID REBOUND (timing-based LONG après falling knife)
print('Generating v29_post_avoid...')
write_version(
    "v29_post_avoid",
    [
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_post_avoid_long": True,             # v29 : LONG après AVOID rebound\n        "hyd_bounce_size": 30,'),
    ],
    "v29 POST_AVOID — après zone AVOID (falling knife), achat sur rebound mean-revert.\n"
    "Hypothèse : le marché rebound systématiquement après une chute brutale.\n"
    "Live attendu : +22,000 à +24,500. Risque -1k si pas de rebound."
)

# v31 : VEV_4000 INSIDE AGGRESSIVE (force penny inside, ignore queue)
print('Generating v31_4000_inside...')
write_version(
    "v31_4000_inside",
    [
        ('"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,',
         '"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,\n        "vev_4000_inside_aggressive": (_strike == 4000),'),
    ],
    "v31 VEV_4000_INSIDE — force quotes inside (bb+1 / ba-1) sur VEV_4000.\n"
    "Codex : passive markout +9.7/+10.2 si captured, capacity +4,500 sur 3j.\n"
    "401365 capture seulement +52 → queue priority. Force inside = bypass queue.\n"
    "Live attendu : -2k worst à +3k best. EXPÉRIMENTAL."
)

# v32 : COMBO AUDACIEUX (BIG_SIGNAL + LONG_LITE + 5400 SELL + POST_AVOID)
print('Generating v32_combo_audacious...')
write_version(
    "v32_combo_audacious",
    [
        ('_VEV_DISABLED = {5200, 5300, 5400, 5500, 6000, 6500}',
         '_VEV_DISABLED = {5200, 5300, 5500, 6000, 6500}'),
        ('"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,',
         '"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,\n        "vev_5400_sell_overlay": (_strike == 5400),\n        "vev_5400_sell_size": 5,'),
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_long_lite_enable": True,\n        "hyd_big_signal": True,\n        "hyd_short_big_size": 60,\n        "hyd_post_avoid_long": True,\n        "hyd_bounce_size": 30,'),
    ],
    "v32 COMBO AUDACIEUX — v12 + 5400 SELL + LONG_LITE + BIG_SIGNAL + POST_AVOID.\n"
    "Empile 4 signaux théoriquement orthogonaux. Le live peut tout valider ou tout casser.\n"
    "Live attendu : -3k à +8k vs v12. Variance maximale."
)

# v33 : ULTRA-AGGRESSIVE (combo + VEV_4000 inside)
print('Generating v33_ultra...')
write_version(
    "v33_ultra",
    [
        ('_VEV_DISABLED = {5200, 5300, 5400, 5500, 6000, 6500}',
         '_VEV_DISABLED = {5200, 5300, 5500, 6000, 6500}'),
        ('"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,',
         '"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,\n        "vev_5400_sell_overlay": (_strike == 5400),\n        "vev_5400_sell_size": 5,\n        "vev_4000_inside_aggressive": (_strike == 4000),'),
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_long_lite_enable": True,\n        "hyd_big_signal": True,\n        "hyd_short_big_size": 60,\n        "hyd_post_avoid_long": True,\n        "hyd_bounce_size": 30,'),
    ],
    "v33 ULTRA — v32 + VEV_4000 forced inside.\n"
    "Tout empilé incluant les patches expérimentaux. Variance maximale.\n"
    "Live attendu : -5k à +10k. Le pari le plus extrême."
)


# v34 : COMBO PROPRE — v25 + v28 + v31 (3 patches sans risque backtest catastrophique)
print('Generating v34_combo_clean...')
write_version(
    "v34_combo_clean",
    [
        ('"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,',
         '"position_limit": _limit,\n        "vev_otm_long": _vev_otm_long,\n        "vev_otm_qty": 10,\n        "vev_4000_inside_aggressive": (_strike == 4000),'),
        ('"hyd_short_lite_size": 30,              # v12 single-level',
         '"hyd_short_lite_size": 30,              # v12 single-level\n        "hyd_long_lite_enable": True,           # v25\n        "hyd_big_signal": True,                  # v28\n        "hyd_short_big_size": 60,'),
    ],
    "v34 COMBO_CLEAN — v12 + LONG_LITE + BIG_SIGNAL + VEV_4000 inside.\n"
    "3 patches additifs sans risque catastrophique en backtest.\n"
    "Live attendu : +22,000 à +25,500. Risque -1k worst, gain +3k best."
)

print()
print('=== Versions créées ===')
for v in ["v12_pure", "v23_5400_sell", "v25_long_lite", "v28_big_signal",
          "v29_post_avoid", "v31_4000_inside", "v32_combo_audacious", "v33_ultra",
          "v34_combo_clean"]:
    p = os.path.join(HERE, f"trader_r3_{v}.py")
    if os.path.exists(p):
        size_kb = os.path.getsize(p) / 1024
        print(f'  trader_r3_{v}.py ({size_kb:.0f} KB)')
