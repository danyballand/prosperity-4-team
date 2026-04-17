"""Grid search autour de OFI Osm α=2 hl=20."""
import sys

OSM = "ASH_COATED_OSMIUM"


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
        per_day.append((pnl[OSM], pnl["INTARIAN_PEPPER_ROOT"]))
    return per_day


def mk(alpha, hl):
    def patch(tm):
        tm.PRODUCT_PARAMS[OSM]["use_ofi_correction"] = True
        tm.PRODUCT_PARAMS[OSM]["ofi_alpha"] = alpha
        tm.PRODUCT_PARAMS[OSM]["ofi_halflife"] = hl
    return patch


def baseline(tm): pass


if __name__ == "__main__":
    base = run_variant(baseline)
    base_tot = sum(o + p for o, p in base)
    print(f"baseline: {base_tot:+.0f}")
    print(f"{'alpha':>6} {'hl':>6} {'Osm_d-2':>9} {'Osm_d-1':>9} {'Osm_d0':>9} {'Osm_tot':>9} {'dTOT':>7}")
    for alpha in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        for hl in [5, 10, 15, 20, 30, 50, 100]:
            pd = run_variant(mk(alpha, hl))
            osm_days = [o for o, _ in pd]
            osm_tot = sum(osm_days)
            base_osm_tot = sum(o for o, _ in base)
            d_osm = osm_tot - base_osm_tot
            print(f"{alpha:>6.1f} {hl:>6.0f} {osm_days[0]:>+9.0f} {osm_days[1]:>+9.0f} {osm_days[2]:>+9.0f} {osm_tot:>+9.0f} {d_osm:>+7.0f}")
