"""
Test matrix for v32 add-ons.
Usage : cp trader_v32.py trader.py PUIS python3 retest_v32_addons.py PUIS restore.
On teste chaque add-on isolé + combinaisons, sur les 3 jours R1.
"""
import sys

OSM = "ASH_COATED_OSMIUM"
PEP = "INTARIAN_PEPPER_ROOT"


def reset_trader_module():
    for mod_name in ["trader", "local_backtest_v3"]:
        if mod_name in sys.modules:
            del sys.modules[mod_name]


def run_variant(patch_fn):
    reset_trader_module()
    import trader as tm
    import local_backtest_v3 as bt
    patch_fn(tm)
    per_day = []
    for day in [-2, -1, 0]:
        pnl, _, _, _ = bt.simulate(day, passive_fills=True)
        per_day.append((pnl[OSM], pnl[PEP]))
    return per_day


def fmt_line(name, per_day, base):
    totals = [o + p for o, p in per_day]
    grand = sum(totals)
    base_totals = [o + p for o, p in base]
    base_grand = sum(base_totals)
    delta = grand - base_grand
    # Osm vs Pep decomposition
    osm_tot = sum(o for o, _ in per_day)
    pep_tot = sum(p for _, p in per_day)
    base_osm = sum(o for o, _ in base)
    base_pep = sum(p for _, p in base)
    d_osm = osm_tot - base_osm
    d_pep = pep_tot - base_pep
    mark = "**" if delta > 300 else " +" if delta > 50 else "  " if abs(delta) <= 50 else " -" if delta > -300 else "XX"
    return f"{mark} {name:<48} Osm={d_osm:>+6.0f}  Pep={d_pep:>+6.0f}  TOT={delta:>+6.0f}  (grand={grand:>+7.0f})"


# =================== VARIANTS ===================

def baseline(tm): pass

# --- OFI isolé ---
def ofi_osm_alpha1(tm):
    tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = 10.0
    tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = 1.0
def ofi_osm_alpha2(tm):
    tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = 10.0
    tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = 2.0
def ofi_osm_alpha5(tm):
    tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = 10.0
    tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = 5.0
def ofi_osm_hl5_a2(tm):
    tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = 5.0
    tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = 2.0
def ofi_osm_hl20_a2(tm):
    tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = 20.0
    tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = 2.0
def ofi_pep_a2(tm):
    tm.PRODUCT_PARAMS[PEP]["use_ofi_correction"] = True
    tm.PRODUCT_PARAMS[PEP]["ofi_halflife"] = 10.0
    tm.PRODUCT_PARAMS[PEP]["ofi_alpha"] = 2.0
def ofi_both_a2(tm):
    for p in (OSM, PEP):
        tm.PRODUCT_PARAMS[p]["use_ofi_correction"] = True
        tm.PRODUCT_PARAMS[p]["ofi_halflife"] = 10.0
        tm.PRODUCT_PARAMS[p]["ofi_alpha"] = 2.0

# --- Toxicity isolé ---
def tox_osm_cap15(tm):
    tm.PRODUCT_PARAMS[OSM]["use_toxicity"] = True
    tm.PRODUCT_PARAMS[OSM]["tox_halflife"] = 30.0
    tm.PRODUCT_PARAMS[OSM]["tox_horizon"] = 20
    tm.PRODUCT_PARAMS[OSM]["tox_theta"] = 1.0
    tm.PRODUCT_PARAMS[OSM]["tox_cap"] = 1.5
def tox_osm_cap20(tm):
    tm.PRODUCT_PARAMS[OSM]["use_toxicity"] = True
    tm.PRODUCT_PARAMS[OSM]["tox_halflife"] = 30.0
    tm.PRODUCT_PARAMS[OSM]["tox_horizon"] = 20
    tm.PRODUCT_PARAMS[OSM]["tox_theta"] = 1.0
    tm.PRODUCT_PARAMS[OSM]["tox_cap"] = 2.0
def tox_osm_theta2(tm):
    tm.PRODUCT_PARAMS[OSM]["use_toxicity"] = True
    tm.PRODUCT_PARAMS[OSM]["tox_halflife"] = 30.0
    tm.PRODUCT_PARAMS[OSM]["tox_horizon"] = 20
    tm.PRODUCT_PARAMS[OSM]["tox_theta"] = 2.0
    tm.PRODUCT_PARAMS[OSM]["tox_cap"] = 1.5
def tox_osm_hz50(tm):
    tm.PRODUCT_PARAMS[OSM]["use_toxicity"] = True
    tm.PRODUCT_PARAMS[OSM]["tox_halflife"] = 50.0
    tm.PRODUCT_PARAMS[OSM]["tox_horizon"] = 50
    tm.PRODUCT_PARAMS[OSM]["tox_theta"] = 1.0
    tm.PRODUCT_PARAMS[OSM]["tox_cap"] = 1.5
def tox_pep_cap15(tm):
    tm.PRODUCT_PARAMS[PEP]["use_toxicity"] = True
    tm.PRODUCT_PARAMS[PEP]["tox_halflife"] = 30.0
    tm.PRODUCT_PARAMS[PEP]["tox_horizon"] = 20
    tm.PRODUCT_PARAMS[PEP]["tox_theta"] = 1.0
    tm.PRODUCT_PARAMS[PEP]["tox_cap"] = 1.5

# --- Queue-skip isolé ---
def qs_osm_t20(tm):
    tm.PRODUCT_PARAMS[OSM]["use_queue_skip"] = True
    tm.PRODUCT_PARAMS[OSM]["queue_skip_threshold"] = 20
def qs_osm_t40(tm):
    tm.PRODUCT_PARAMS[OSM]["use_queue_skip"] = True
    tm.PRODUCT_PARAMS[OSM]["queue_skip_threshold"] = 40
def qs_osm_t80(tm):
    tm.PRODUCT_PARAMS[OSM]["use_queue_skip"] = True
    tm.PRODUCT_PARAMS[OSM]["queue_skip_threshold"] = 80
def qs_osm_t150(tm):
    tm.PRODUCT_PARAMS[OSM]["use_queue_skip"] = True
    tm.PRODUCT_PARAMS[OSM]["queue_skip_threshold"] = 150
def qs_pep_t40(tm):
    tm.PRODUCT_PARAMS[PEP]["use_queue_skip"] = True
    tm.PRODUCT_PARAMS[PEP]["queue_skip_threshold"] = 40

# --- Combos à lancer seulement si un add-on émerge isolé ---


VARIANTS = [
    ("baseline v31", baseline),
    ("ofi_osm a=1 hl=10", ofi_osm_alpha1),
    ("ofi_osm a=2 hl=10", ofi_osm_alpha2),
    ("ofi_osm a=5 hl=10", ofi_osm_alpha5),
    ("ofi_osm a=2 hl=5",  ofi_osm_hl5_a2),
    ("ofi_osm a=2 hl=20", ofi_osm_hl20_a2),
    ("ofi_pep a=2 hl=10", ofi_pep_a2),
    ("ofi_both a=2 hl=10", ofi_both_a2),
    ("tox_osm cap=1.5 th=1", tox_osm_cap15),
    ("tox_osm cap=2.0 th=1", tox_osm_cap20),
    ("tox_osm cap=1.5 th=2", tox_osm_theta2),
    ("tox_osm hz=50 cap=1.5",  tox_osm_hz50),
    ("tox_pep cap=1.5 th=1", tox_pep_cap15),
    ("qs_osm th=20",  qs_osm_t20),
    ("qs_osm th=40",  qs_osm_t40),
    ("qs_osm th=80",  qs_osm_t80),
    ("qs_osm th=150", qs_osm_t150),
    ("qs_pep th=40",  qs_pep_t40),
]


if __name__ == "__main__":
    print("=== V32 ADD-ON MATRIX (3 jours R1) ===")
    base = run_variant(baseline)
    base_totals = [o + p for o, p in base]
    print(f"   baseline v31                                     "
          f"d-2={base_totals[0]:>+7.0f}  d-1={base_totals[1]:>+7.0f}  d0={base_totals[2]:>+7.0f}  "
          f"TOT={sum(base_totals):>+7.0f}")
    print("-" * 100)
    print("   {:<48} {:>6}  {:>6}  {:>6}".format("variant", "dOsm", "dPep", "dTOT"))
    print("-" * 100)
    for name, fn in VARIANTS[1:]:
        pd = run_variant(fn)
        print(fmt_line(name, pd, base))
    print("-" * 100)
    print("Legend: ** > +300  +> +50  (space) < |50|  - > -300  XX < -300")
