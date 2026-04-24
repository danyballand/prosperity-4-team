#!/usr/bin/env python3
"""
Round 3 spreads/stat-arb analysis for IMC Prosperity-style VE options.

Outputs:
  - arb_opportunities.csv
  - fly_timeseries_by_triplet.png
  - correlation_matrix.png
  - synthetic_ve_vs_real.png
  - cointegration_pvalues_matrix.png
  - report.md

The script intentionally depends only on pandas/numpy/Pillow so it can run in
the bundled Codex Python runtime without installing statsmodels/matplotlib.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


PRODUCT_VE = "VELVETFRUIT_EXTRACT"
PRODUCT_HYD = "HYDROGEL_PACK"
TRADING_DAYS_PER_YEAR = 365.0
DEFAULT_DATA_DIR = Path("/Users/danyballand/Downloads/ROUND_3")


@dataclass(frozen=True)
class FlySpec:
    k1: int
    k2: int
    k3: int

    @property
    def name(self) -> str:
        return f"{self.k1}-{self.k2}-{self.k3}"

    @property
    def weights(self) -> tuple[float, float, float]:
        """Convexity portfolio weights: w1*C1 - C2 + w3*C3."""
        w1 = (self.k3 - self.k2) / (self.k3 - self.k1)
        w3 = (self.k2 - self.k1) / (self.k3 - self.k1)
        return w1, -1.0, w3

    @property
    def is_equal_spaced(self) -> bool:
        return (self.k2 - self.k1) == (self.k3 - self.k2)


def norm_cdf(x: np.ndarray | float) -> np.ndarray | float:
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2.0)))


def bs_call_price(s: np.ndarray, k: float, sigma: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    t = np.asarray(t, dtype=float)
    t = np.maximum(t, 1e-9)
    sigma = np.maximum(sigma, 1e-9)
    d1 = (np.log(np.maximum(s, 1e-9) / k) + 0.5 * sigma * sigma * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    return s * norm_cdf(d1) - k * norm_cdf(d2)


def bs_call_delta(s: np.ndarray, k: float, sigma: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    t = np.asarray(t, dtype=float)
    t = np.maximum(t, 1e-9)
    sigma = np.maximum(sigma, 1e-9)
    d1 = (np.log(np.maximum(s, 1e-9) / k) + 0.5 * sigma * sigma * t) / (sigma * np.sqrt(t))
    return norm_cdf(d1)


def implied_vol_vectorized(s: np.ndarray, k: float, price: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    """Bisection implied vol for calls, vectorized over rows."""
    s = np.asarray(s, dtype=float)
    price = np.asarray(price, dtype=float)
    t_arr = np.asarray(t, dtype=float) + np.zeros_like(s)
    intrinsic = np.maximum(s - k, 0.0)
    upper = np.maximum(s, 1e-9)
    valid = (price >= intrinsic - 1e-6) & (price <= upper + 1e-6)
    lo = np.full_like(s, 1e-6, dtype=float)
    hi = np.full_like(s, 5.0, dtype=float)
    out = np.full_like(s, np.nan, dtype=float)
    if not np.any(valid):
        return out
    lo_v = lo[valid]
    hi_v = hi[valid]
    s_v = s[valid]
    p_v = np.maximum(price[valid], intrinsic[valid])
    t_v = np.maximum(t_arr[valid], 1e-9)
    for _ in range(60):
        mid = (lo_v + hi_v) / 2.0
        model = bs_call_price(s_v, k, mid, t_v)
        hi_v = np.where(model > p_v, mid, hi_v)
        lo_v = np.where(model <= p_v, mid, lo_v)
    out[valid] = (lo_v + hi_v) / 2.0
    return out


def load_prices(data_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(data_dir.glob("prices_round_3_day_*.csv")):
        frame = pd.read_csv(path, sep=";")
        frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No prices_round_3_day_*.csv files found in {data_dir}")
    df = pd.concat(frames, ignore_index=True)
    df["day"] = df["day"].astype(int)
    df["timestamp"] = df["timestamp"].astype(int)
    df["global_ts"] = df["day"] * 1_000_000 + df["timestamp"]
    for col in [
        "bid_price_1",
        "ask_price_1",
        "mid_price",
        "bid_volume_1",
        "ask_volume_1",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def strike_from_product(product: str) -> int | None:
    match = re.fullmatch(r"VEV_(\d+)", product)
    return int(match.group(1)) if match else None


def build_wide(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    wide = df.pivot_table(index=["day", "timestamp", "global_ts"], columns="product", values=value_col)
    wide = wide.sort_index()
    return wide


def half_spread_from_wide(ask: pd.DataFrame, bid: pd.DataFrame) -> pd.DataFrame:
    hs = (ask - bid) / 2.0
    return hs.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def estimate_half_life(series: pd.Series) -> tuple[float, float]:
    x = series.dropna().to_numpy(dtype=float)
    if len(x) < 3 or np.nanstd(x) < 1e-12:
        return math.nan, math.nan
    centered = x - np.nanmean(x)
    y = centered[1:]
    xlag = centered[:-1]
    denom = np.dot(xlag, xlag)
    if denom <= 1e-12:
        return math.nan, math.nan
    rho = float(np.dot(xlag, y) / denom)
    if 0.0 < rho < 1.0:
        return float(-math.log(2.0) / math.log(rho)), rho
    if rho >= 1.0:
        return math.inf, rho
    return 0.0, rho


def run_mean_reversion_strategy(
    value: pd.Series,
    cost: pd.Series,
    entry_z: float = -2.0,
    exit_z: float = 0.0,
) -> dict[str, float]:
    data = pd.concat({"value": value, "cost": cost}, axis=1).dropna()
    if len(data) < 10 or data["value"].std() <= 1e-12:
        return {"trades": 0, "ev": math.nan, "win_rate": math.nan, "worst": math.nan}
    z = (data["value"] - data["value"].mean()) / data["value"].std()
    in_trade = False
    entry_value = entry_cost = 0.0
    pnls: list[float] = []
    for idx, zval in z.items():
        row = data.loc[idx]
        if not in_trade and zval < entry_z:
            in_trade = True
            entry_value = float(row["value"])
            entry_cost = float(row["cost"])
        elif in_trade and zval > exit_z:
            exit_value = float(row["value"])
            exit_cost = float(row["cost"])
            pnls.append(exit_value - entry_value - entry_cost - exit_cost)
            in_trade = False
    if not pnls:
        return {"trades": 0, "ev": math.nan, "win_rate": math.nan, "worst": math.nan}
    arr = np.asarray(pnls, dtype=float)
    return {
        "trades": int(len(arr)),
        "ev": float(np.mean(arr)),
        "win_rate": float(np.mean(arr > 0.0)),
        "worst": float(np.min(arr)),
    }


def analyze_flies(
    mid: pd.DataFrame,
    bid: pd.DataFrame,
    ask: pd.DataFrame,
    half_spread: pd.DataFrame,
    strikes: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fly_rows = []
    daily_rows = []
    fly_series = {}
    for k1, k2, k3 in zip(strikes[:-2], strikes[1:-1], strikes[2:]):
        spec = FlySpec(k1, k2, k3)
        p1, p2, p3 = f"VEV_{k1}", f"VEV_{k2}", f"VEV_{k3}"
        w1, w2, w3 = spec.weights
        simple_fly = mid[p1] - 2.0 * mid[p2] + mid[p3]
        convexity_fly = w1 * mid[p1] + w2 * mid[p2] + w3 * mid[p3]
        tradable_edge = bid[p2] - (w1 * ask[p1] + w3 * ask[p3])
        strategy_cost = (
            abs(w1) * half_spread[p1] + abs(w2) * half_spread[p2] + abs(w3) * half_spread[p3]
        ) * 2.0
        fly_series[spec.name] = convexity_fly.reset_index()

        for day, day_values in convexity_fly.groupby(level="day"):
            simple_day = simple_fly.xs(day, level="day")
            conv_day = day_values.droplevel("day")
            edge_day = tradable_edge.xs(day, level="day")
            cost_day = strategy_cost.xs(day, level="day")
            hl, rho = estimate_half_life(conv_day)
            strat = run_mean_reversion_strategy(conv_day, cost_day)
            violations_mid = int((conv_day < -1e-9).sum())
            tradable_violations = int((edge_day > 1e-9).sum())
            daily_rows.append(
                {
                    "K1": k1,
                    "K2": k2,
                    "K3": k3,
                    "day": int(day),
                    "equal_spaced": spec.is_equal_spaced,
                    "violations_count_mid": violations_mid,
                    "tradable_arb_count": tradable_violations,
                    "mean_fly": float(simple_day.mean()),
                    "std_fly": float(simple_day.std()),
                    "min_fly": float(simple_day.min()),
                    "max_fly": float(simple_day.max()),
                    "mean_convexity_fly": float(conv_day.mean()),
                    "std_convexity_fly": float(conv_day.std()),
                    "min_convexity_fly": float(conv_day.min()),
                    "max_tradable_edge": float(edge_day.max()),
                    "half_life": hl,
                    "autocorr_rho": rho,
                    "strategy_trades": strat["trades"],
                    "EV_trade_estimated": strat["ev"],
                    "strategy_win_rate": strat["win_rate"],
                    "strategy_worst_trade": strat["worst"],
                }
            )

        all_hl, all_rho = estimate_half_life(convexity_fly)
        all_strat = run_mean_reversion_strategy(convexity_fly, strategy_cost)
        fly_rows.append(
            {
                "type": "butterfly_convexity",
                "product_a": p1,
                "product_b": p2,
                "product_c": p3,
                "K1": k1,
                "K2": k2,
                "K3": k3,
                "direction": "buy convex fly when z<-2, close z>0",
                "EV_par_trade": all_strat["ev"],
                "opportunities_per_day": all_strat["trades"] / 3.0,
                "capital_required_ticks": float(
                    (abs(w1) * mid[p1] + abs(w2) * mid[p2] + abs(w3) * mid[p3]).median()
                ),
                "risk_max_ticks": all_strat["worst"],
                "frequency_count": all_strat["trades"],
                "tradable_arb_count": int((tradable_edge > 1e-9).sum()),
                "max_tradable_edge": float(tradable_edge.max()),
                "score": safe_score(all_strat["ev"], all_strat["trades"], all_strat["worst"]),
                "notes": f"mid convexity violations={(convexity_fly < -1e-9).sum()}, half_life={all_hl:.2f}, rho={all_rho:.4f}",
            }
        )
    return pd.DataFrame(daily_rows), pd.DataFrame(fly_rows), fly_series_to_frame(fly_series)


def fly_series_to_frame(fly_series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged = None
    for name, frame in fly_series.items():
        small = frame[["day", "timestamp", "global_ts", 0]].rename(columns={0: name})
        if merged is None:
            merged = small
        else:
            merged = merged.merge(small, on=["day", "timestamp", "global_ts"], how="outer")
    return merged.sort_values(["day", "timestamp"]) if merged is not None else pd.DataFrame()


def analyze_vertical_pairs(
    mid: pd.DataFrame,
    bid: pd.DataFrame,
    ask: pd.DataFrame,
    half_spread: pd.DataFrame,
    strikes: list[int],
) -> pd.DataFrame:
    rows = []
    for k1, k2 in zip(strikes[:-1], strikes[1:]):
        p1, p2 = f"VEV_{k1}", f"VEV_{k2}"
        diff = mid[p1] - mid[p2]
        monotonic_edge = bid[p2] - ask[p1]
        max_width_edge = bid[p1] - ask[p2] - (k2 - k1)
        spread_cost = 2.0 * (half_spread[p1] + half_spread[p2])
        hl, rho = estimate_half_life(diff)
        strat = run_mean_reversion_strategy(diff - diff.mean(), spread_cost)
        rows.append(
            {
                "type": "vertical_pair",
                "product_a": p1,
                "product_b": p2,
                "product_c": "",
                "K1": k1,
                "K2": k2,
                "K3": "",
                "direction": "mean-revert call-spread width",
                "EV_par_trade": strat["ev"],
                "opportunities_per_day": strat["trades"] / 3.0,
                "capital_required_ticks": float((mid[p1].abs() + mid[p2].abs()).median()),
                "risk_max_ticks": strat["worst"],
                "frequency_count": strat["trades"],
                "tradable_arb_count": int(((monotonic_edge > 1e-9) | (max_width_edge > 1e-9)).sum()),
                "max_tradable_edge": float(max(monotonic_edge.max(), max_width_edge.max())),
                "score": safe_score(strat["ev"], strat["trades"], strat["worst"]),
                "notes": (
                    f"monotonic_mid_violations={(diff < -1e-9).sum()}, "
                    f"width_mid_violations={(diff > (k2 - k1) + 1e-9).sum()}, "
                    f"half_life={hl:.2f}, rho={rho:.4f}"
                ),
            }
        )
    return pd.DataFrame(rows)


def safe_score(ev: float, count: float, worst: float) -> float:
    if ev is None or not np.isfinite(ev):
        return -1e9
    penalty = abs(worst) if worst is not None and np.isfinite(worst) and worst < 0 else 1.0
    return float(ev * math.sqrt(max(count, 1.0)) / max(penalty, 1.0))


def confirm_calls(mid: pd.DataFrame, strikes: list[int]) -> pd.DataFrame:
    ve = mid[PRODUCT_VE]
    rows = []
    for k in strikes:
        product = f"VEV_{k}"
        price = mid[product]
        level_corr = float(price.corr(ve))
        ret_corr = float(price.diff().corr(ve.diff()))
        rows.append({"product": product, "strike": k, "level_corr_vs_VE": level_corr, "return_corr_vs_VE": ret_corr})
    return pd.DataFrame(rows)


def analyze_theta(mid: pd.DataFrame, bid: pd.DataFrame, ask: pd.DataFrame, strikes: list[int]) -> pd.DataFrame:
    rows = []
    eod = mid.groupby(level="day").tail(1)
    eod_index_days = [idx[0] for idx in eod.index]
    eod_by_day = {idx[0]: eod.loc[idx] for idx in eod.index}
    for prev_day, cur_day in zip(eod_index_days[:-1], eod_index_days[1:]):
        prev = eod_by_day[prev_day]
        cur = eod_by_day[cur_day]
        s_prev = float(prev[PRODUCT_VE])
        for k in strikes:
            product = f"VEV_{k}"
            price_prev = float(prev[product])
            price_cur = float(cur[product])
            t_prev = max((7.0 - float(prev_day)) / TRADING_DAYS_PER_YEAR, 1e-9)
            t_cur = max((7.0 - float(cur_day)) / TRADING_DAYS_PER_YEAR, 1e-9)
            iv_prev = implied_vol_vectorized(np.array([s_prev]), k, np.array([price_prev]), np.array([t_prev]))[0]
            if not np.isfinite(iv_prev):
                continue
            theta_price = float(bs_call_price(np.array([s_prev]), k, np.array([iv_prev]), np.array([t_cur]))[0])
            theta_decay = price_prev - theta_price
            realized_decay = price_prev - price_cur
            spread_cost = float(
                (ask[f"VEV_{k}"].xs(cur_day, level="day").iloc[-1] - bid[f"VEV_{k}"].xs(cur_day, level="day").iloc[-1])
            )
            edge = realized_decay - theta_decay - spread_cost
            if edge > 0:
                direction = "long after over-decay"
                ev = edge
            elif -edge > 0:
                direction = "short after under-decay"
                ev = -edge
            else:
                direction = "none"
                ev = 0.0
            rows.append(
                {
                    "type": "theta_calendar_proxy",
                    "product_a": product,
                    "product_b": "",
                    "product_c": "",
                    "K1": k,
                    "K2": "",
                    "K3": "",
                    "day_pair": f"{prev_day}->{cur_day}",
                    "direction": direction,
                    "realized_decay": realized_decay,
                    "bs_theta_decay": theta_decay,
                    "edge_after_spread": edge,
                    "EV_par_trade": ev,
                    "opportunities_per_day": 1.0 / 3.0 if abs(edge) > 0 else 0.0,
                    "capital_required_ticks": price_cur,
                    "risk_max_ticks": np.nan,
                    "frequency_count": 1 if abs(edge) > 0 else 0,
                    "tradable_arb_count": 0,
                    "max_tradable_edge": np.nan,
                    "score": ev * 0.05,
                    "notes": "low-confidence theta-only proxy; underlying move is not delta-adjusted",
                }
            )
    return pd.DataFrame(rows)


def analyze_hyd_correlations(mid: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    returns = mid.diff().dropna()
    corr = returns.corr()
    rows = []
    hyd_returns = returns[PRODUCT_HYD]
    for product in mid.columns:
        if product == PRODUCT_HYD:
            continue
        full_corr = float(hyd_returns.corr(returns[product]))
        rolling = hyd_returns.rolling(250).corr(returns[product])
        max_abs_rolling = float(rolling.abs().max())
        rows.append(
            {
                "product": product,
                "return_corr_with_HYD": full_corr,
                "max_abs_rolling_corr_250": max_abs_rolling,
                "pair_trade_candidate": bool(abs(full_corr) > 0.3 or max_abs_rolling > 0.3),
            }
        )
    return pd.DataFrame(rows), corr


def analyze_synthetic(
    mid: pd.DataFrame,
    bid: pd.DataFrame,
    ask: pd.DataFrame,
    half_spread: pd.DataFrame,
    strikes: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    synth_trace = pd.DataFrame(index=mid.index)
    synth_trace["VE_real"] = mid[PRODUCT_VE]

    for k in strikes:
        product = f"VEV_{k}"
        synth = mid[product] + float(k)
        residual = synth - mid[PRODUCT_VE]
        # True one-sided lower-bound arb for calls:
        # if C + K < S, buy call, sell spot, hold K cash. Terminal payoff is a put >= 0.
        # The reverse direction would require a listed put to be riskless, so it is
        # tracked only as residual context in notes and is not counted as tradable arb.
        buy_call_sell_ve_edge = bid[PRODUCT_VE] - (ask[product] + k)
        cost = 2.0 * (half_spread[product] + half_spread[PRODUCT_VE])
        strat = run_mean_reversion_strategy(-residual.abs(), cost)
        tradable_count = int((buy_call_sell_ve_edge > 0).sum())
        max_lower_bound_edge = float(buy_call_sell_ve_edge.max())
        deep_itm = bool(k < mid[PRODUCT_VE].min())
        stat_ev = strat["ev"] if np.isfinite(strat["ev"]) else np.nan
        ev_for_rank = max_lower_bound_edge if tradable_count > 0 else stat_ev
        rows.append(
            {
                "type": "synthetic_deep_itm",
                "product_a": product,
                "product_b": PRODUCT_VE,
                "product_c": "",
                "K1": k,
                "K2": "",
                "K3": "",
                "direction": "buy VEV_K, sell VE only if C+K < S after bid/ask",
                "EV_par_trade": ev_for_rank,
                "opportunities_per_day": tradable_count / 3.0 if tradable_count else strat["trades"] / 3.0,
                "capital_required_ticks": float((mid[product] + mid[PRODUCT_VE]).median()),
                "risk_max_ticks": strat["worst"],
                "frequency_count": tradable_count if tradable_count else strat["trades"],
                "tradable_arb_count": tradable_count,
                "max_tradable_edge": max_lower_bound_edge,
                "score": safe_score(ev_for_rank, tradable_count if tradable_count else strat["trades"], strat["worst"])
                if deep_itm or tradable_count
                else -1.0,
                "notes": (
                    f"deep_itm_all_sample={deep_itm}; residual mean={residual.mean():.3f}, std={residual.std():.3f}; "
                    f"max buy_call_sell_VE_edge={buy_call_sell_ve_edge.max():.3f}; "
                    f"reverse edge ignored without listed puts; mr_ev={strat['ev']}"
                ),
            }
        )
        if k in (4000, 4500, 5000):
            synth_trace[f"{product}_plus_K"] = synth

    # Static OLS replication of VE from all VEV mids. Train on days 0-1, evaluate all days.
    vev_cols = [f"VEV_{k}" for k in strikes]
    train_mask = mid.index.get_level_values("day") <= 1
    x_train = mid.loc[train_mask, vev_cols].to_numpy(dtype=float)
    y_train = mid.loc[train_mask, PRODUCT_VE].to_numpy(dtype=float)
    x_all = mid[vev_cols].to_numpy(dtype=float)
    x_train_i = np.column_stack([np.ones(len(x_train)), x_train])
    x_all_i = np.column_stack([np.ones(len(x_all)), x_all])
    coef, *_ = np.linalg.lstsq(x_train_i, y_train, rcond=None)
    synth_ols = x_all_i @ coef
    synth_trace["OLS_all_calls"] = synth_ols
    residual = pd.Series(synth_ols, index=mid.index) - mid[PRODUCT_VE]
    ols_cost = 2.0 * (
        half_spread[PRODUCT_VE] + sum(abs(coef[i + 1]) * half_spread[vev_cols[i]] for i in range(len(vev_cols)))
    )
    strat = run_mean_reversion_strategy(residual, ols_cost)
    rows.append(
        {
            "type": "synthetic_ols_all_calls",
            "product_a": "ALL_VEVS",
            "product_b": PRODUCT_VE,
            "product_c": "",
            "K1": "",
            "K2": "",
            "K3": "",
            "direction": "OLS stat-arb residual, train day0-1",
            "EV_par_trade": strat["ev"],
            "opportunities_per_day": strat["trades"] / 3.0,
            "capital_required_ticks": float(np.median(np.abs(x_all @ coef[1:]))),
            "risk_max_ticks": strat["worst"],
            "frequency_count": strat["trades"],
            "tradable_arb_count": 0,
            "max_tradable_edge": np.nan,
            "score": safe_score(strat["ev"], strat["trades"], strat["worst"]),
            "notes": (
                f"intercept={coef[0]:.3f}; residual mean={residual.mean():.3f}, std={residual.std():.3f}; "
                f"weights={dict(zip(vev_cols, np.round(coef[1:], 4)))}"
            ),
        }
    )
    synth_trace = synth_trace.reset_index()
    return pd.DataFrame(rows), synth_trace


def adf_tstat(series: pd.Series, max_lag: int = 1) -> float:
    x = series.dropna().to_numpy(dtype=float)
    if len(x) < max_lag + 20 or np.nanstd(x) < 1e-12:
        return math.nan
    dx = np.diff(x)
    y = dx[max_lag:]
    level_lag = x[max_lag:-1]
    columns = [np.ones_like(level_lag), level_lag]
    for lag in range(1, max_lag + 1):
        columns.append(dx[max_lag - lag : -lag])
    xmat = np.column_stack(columns)
    beta, *_ = np.linalg.lstsq(xmat, y, rcond=None)
    resid = y - xmat @ beta
    dof = max(len(y) - xmat.shape[1], 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    xtx_inv = np.linalg.pinv(xmat.T @ xmat)
    se = math.sqrt(max(sigma2 * xtx_inv[1, 1], 1e-18))
    return float(beta[1] / se)


def approx_eg_pvalue(tstat: float) -> float:
    """Rough Engle-Granger residual ADF p-value interpolation.

    Critical values vary with sample size and regressors; this is used for
    ranking, not publication-grade inference.
    """
    if not np.isfinite(tstat):
        return math.nan
    knots = [
        (-4.20, 0.001),
        (-3.90, 0.005),
        (-3.34, 0.010),
        (-2.86, 0.050),
        (-2.57, 0.100),
        (-1.95, 0.500),
        (-1.50, 0.800),
        (0.00, 0.990),
    ]
    if tstat <= knots[0][0]:
        return knots[0][1]
    for (x0, p0), (x1, p1) in zip(knots[:-1], knots[1:]):
        if x0 <= tstat <= x1:
            frac = (tstat - x0) / (x1 - x0)
            return float(p0 + frac * (p1 - p0))
    return 0.999


def analyze_cointegration(
    mid: pd.DataFrame,
    half_spread: pd.DataFrame,
    strikes: list[int],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [f"VEV_{k}" for k in strikes]
    rows = []
    pval_matrix = pd.DataFrame(np.nan, index=cols, columns=cols)
    for i, col_a in enumerate(cols):
        for j, col_b in enumerate(cols):
            if i == j:
                pval_matrix.loc[col_a, col_b] = 0.0
                continue
            if j <= i:
                continue
            x = mid[col_b].to_numpy(dtype=float)
            y = mid[col_a].to_numpy(dtype=float)
            xmat = np.column_stack([np.ones(len(x)), x])
            beta, *_ = np.linalg.lstsq(xmat, y, rcond=None)
            resid = pd.Series(y - xmat @ beta, index=mid.index)
            tstat = adf_tstat(resid, max_lag=1)
            pvalue = approx_eg_pvalue(tstat)
            pval_matrix.loc[col_a, col_b] = pvalue
            pval_matrix.loc[col_b, col_a] = pvalue
            cost = 2.0 * (half_spread[col_a] + abs(beta[1]) * half_spread[col_b])
            strat = run_mean_reversion_strategy(-resid, cost)
            # Also test the symmetric entry direction and keep the better EV.
            strat2 = run_mean_reversion_strategy(resid, cost)
            if (strat2["ev"] if np.isfinite(strat2["ev"]) else -1e9) > (
                strat["ev"] if np.isfinite(strat["ev"]) else -1e9
            ):
                strat = strat2
                direction = f"long residual {col_a} - beta*{col_b} when low"
            else:
                direction = f"short residual {col_a} - beta*{col_b} when high"
            mean_abs_resid = float(resid.abs().mean())
            std_resid = float(resid.std())
            expected_sharpe_proxy = (
                mean_abs_resid / std_resid * max((strat["ev"] if np.isfinite(strat["ev"]) else 0.0), 0.0)
                if std_resid > 1e-12
                else 0.0
            )
            rows.append(
                {
                    "type": "cointegration_pair",
                    "product_a": col_a,
                    "product_b": col_b,
                    "product_c": "",
                    "K1": strike_from_product(col_a),
                    "K2": strike_from_product(col_b),
                    "K3": "",
                    "direction": direction,
                    "beta": float(beta[1]),
                    "intercept": float(beta[0]),
                    "adf_tstat": tstat,
                    "pvalue_approx": pvalue,
                    "EV_par_trade": strat["ev"],
                    "opportunities_per_day": strat["trades"] / 3.0,
                    "capital_required_ticks": float((mid[col_a].abs() + abs(beta[1]) * mid[col_b].abs()).median()),
                    "risk_max_ticks": strat["worst"],
                    "frequency_count": strat["trades"],
                    "tradable_arb_count": 0,
                    "max_tradable_edge": np.nan,
                    "score": safe_score(strat["ev"], strat["trades"], strat["worst"]) + (0.05 - min(pvalue, 0.05)),
                    "notes": f"mean_abs_resid={mean_abs_resid:.3f}, std_resid={std_resid:.3f}, sharpe_proxy={expected_sharpe_proxy:.3f}",
                }
            )
    return pd.DataFrame(rows), pval_matrix


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fill=(30, 30, 30), font=None) -> None:
    draw.text(xy, text, fill=fill, font=font)


def load_font(size: int = 12) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def color_gradient(value: float, vmin: float, vmax: float, inverse: bool = False) -> tuple[int, int, int]:
    if not np.isfinite(value):
        return (235, 235, 235)
    if vmax <= vmin:
        z = 0.5
    else:
        z = (value - vmin) / (vmax - vmin)
    z = min(max(z, 0.0), 1.0)
    if inverse:
        z = 1.0 - z
    # Blue-white-red diverging-ish scale with restrained saturation.
    if z < 0.5:
        f = z / 0.5
        return (int(70 + 185 * f), int(115 + 140 * f), int(190 + 55 * f))
    f = (z - 0.5) / 0.5
    return (int(255 - 35 * f), int(255 - 155 * f), int(255 - 145 * f))


def plot_heatmap(matrix: pd.DataFrame, output: Path, title: str, vmin: float, vmax: float, inverse: bool = False) -> None:
    labels = list(matrix.index)
    n = len(labels)
    cell = 50
    left = 150
    top = 80
    width = left + n * cell + 30
    height = top + n * cell + 80
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = load_font(11)
    title_font = load_font(18)
    draw_text(draw, (20, 20), title, font=title_font)
    for i, label in enumerate(labels):
        draw_text(draw, (left + i * cell + 2, top - 22), short_label(label), font=font)
        draw_text(draw, (20, top + i * cell + 17), short_label(label), font=font)
    for r, row_label in enumerate(labels):
        for c, col_label in enumerate(labels):
            val = float(matrix.loc[row_label, col_label])
            x = left + c * cell
            y = top + r * cell
            draw.rectangle([x, y, x + cell, y + cell], fill=color_gradient(val, vmin, vmax, inverse=inverse), outline=(255, 255, 255))
            if np.isfinite(val):
                txt = f"{val:.2f}" if abs(val) >= 0.01 else f"{val:.3f}"
                draw_text(draw, (x + 8, y + 18), txt, fill=(20, 20, 20), font=font)
    img.save(output)


def short_label(label: str) -> str:
    return label.replace("VELVETFRUIT_EXTRACT", "VE").replace("HYDROGEL_PACK", "HYD").replace("VEV_", "V")


def plot_fly_timeseries(fly_ts: pd.DataFrame, output: Path) -> None:
    value_cols = [c for c in fly_ts.columns if c not in {"day", "timestamp", "global_ts"}]
    panels = len(value_cols)
    cols = 2
    rows = math.ceil(panels / cols)
    panel_w = 560
    panel_h = 220
    margin_x = 65
    margin_y = 45
    img = Image.new("RGB", (cols * panel_w, rows * panel_h + 45), "white")
    draw = ImageDraw.Draw(img)
    font = load_font(11)
    title_font = load_font(18)
    draw_text(draw, (20, 15), "Convexity fly time series by adjacent triplet", font=title_font)
    colors = [(32, 94, 160), (210, 112, 50), (45, 135, 90)]
    for idx, col in enumerate(value_cols):
        r, c = divmod(idx, cols)
        x0 = c * panel_w + margin_x
        y0 = r * panel_h + margin_y + 35
        w = panel_w - 95
        h = panel_h - 80
        values = fly_ts[col].to_numpy(dtype=float)
        ts = np.arange(len(values))
        finite = np.isfinite(values)
        if not np.any(finite):
            continue
        vmin = float(np.nanmin(values))
        vmax = float(np.nanmax(values))
        if abs(vmax - vmin) < 1e-9:
            vmax += 1.0
            vmin -= 1.0
        draw.rectangle([x0, y0, x0 + w, y0 + h], outline=(190, 190, 190), fill=(250, 250, 250))
        y_zero = y0 + h - int((0 - vmin) / (vmax - vmin) * h)
        if y0 <= y_zero <= y0 + h:
            draw.line([x0, y_zero, x0 + w, y_zero], fill=(160, 160, 160), width=1)
        for day in sorted(fly_ts["day"].unique()):
            mask = (fly_ts["day"].to_numpy() == day) & finite
            if mask.sum() < 2:
                continue
            x_vals = x0 + ((ts[mask] - ts[finite].min()) / max(ts[finite].max() - ts[finite].min(), 1)) * w
            y_vals = y0 + h - ((values[mask] - vmin) / (vmax - vmin)) * h
            points = list(zip(x_vals.astype(int), y_vals.astype(int)))
            draw.line(points, fill=colors[int(day) % len(colors)], width=2)
        draw_text(draw, (x0, y0 - 22), f"{col}  min={vmin:.2f} max={vmax:.2f}", font=font)
        draw_text(draw, (x0 - 50, y0), f"{vmax:.1f}", font=font)
        draw_text(draw, (x0 - 50, y0 + h - 12), f"{vmin:.1f}", font=font)
    img.save(output)


def plot_synthetic_trace(trace: pd.DataFrame, output: Path) -> None:
    cols = [c for c in trace.columns if c not in {"day", "timestamp", "global_ts"}]
    width, height = 1200, 680
    left, top = 85, 75
    plot_w, plot_h = 1040, 490
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    font = load_font(12)
    title_font = load_font(20)
    draw_text(draw, (30, 25), "Synthetic VE traces vs real VE", font=title_font)
    values = trace[cols].to_numpy(dtype=float)
    vmin = float(np.nanpercentile(values, 1))
    vmax = float(np.nanpercentile(values, 99))
    pad = (vmax - vmin) * 0.05
    vmin -= pad
    vmax += pad
    draw.rectangle([left, top, left + plot_w, top + plot_h], outline=(190, 190, 190), fill=(250, 250, 250))
    colors = [(20, 20, 20), (32, 94, 160), (210, 112, 50), (45, 135, 90), (150, 70, 150)]
    x_axis = np.arange(len(trace))
    for idx, col in enumerate(cols):
        y = trace[col].to_numpy(dtype=float)
        finite = np.isfinite(y)
        if finite.sum() < 2:
            continue
        x_vals = left + ((x_axis[finite] - x_axis[finite].min()) / max(x_axis[finite].max() - x_axis[finite].min(), 1)) * plot_w
        y_vals = top + plot_h - ((y[finite] - vmin) / (vmax - vmin)) * plot_h
        points = list(zip(x_vals.astype(int), y_vals.astype(int)))
        draw.line(points, fill=colors[idx % len(colors)], width=2 if col != "VE_real" else 3)
        draw.rectangle([left + 15, top + plot_h + 25 + idx * 20, left + 28, top + plot_h + 38 + idx * 20], fill=colors[idx % len(colors)])
        draw_text(draw, (left + 35, top + plot_h + 23 + idx * 20), col, font=font)
    draw_text(draw, (20, top), f"{vmax:.1f}", font=font)
    draw_text(draw, (20, top + plot_h - 12), f"{vmin:.1f}", font=font)
    img.save(output)


def write_report(
    output: Path,
    daily_fly: pd.DataFrame,
    opportunities: pd.DataFrame,
    call_check: pd.DataFrame,
    hyd_corr: pd.DataFrame,
    theta: pd.DataFrame,
    pvals: pd.DataFrame,
    synth_trace: pd.DataFrame,
) -> None:
    top = opportunities.sort_values(["score", "EV_par_trade"], ascending=False).head(10)
    top5 = top.head(5)
    best_fly = opportunities[opportunities["type"].eq("butterfly_convexity")].sort_values(
        ["tradable_arb_count", "EV_par_trade"], ascending=False
    )
    coint_all = opportunities[opportunities["type"].eq("cointegration_pair")]
    best_coint = coint_all.sort_values(["pvalue_approx", "adf_tstat", "EV_par_trade"], ascending=[True, True, False])
    best_coint_ev = coint_all[coint_all["EV_par_trade"].fillna(-1e9) > 0].sort_values(
        ["EV_par_trade", "pvalue_approx"], ascending=[False, True]
    )
    best_synth = opportunities[opportunities["type"].str.startswith("synthetic")].sort_values(
        ["tradable_arb_count", "EV_par_trade"], ascending=False
    )

    lines: list[str] = []
    lines.append("# R3 Spreads, baskets & stat arb multi-produits")
    lines.append("")
    lines.append("## Résumé exécutif")
    tradable_fly_count = int(daily_fly["tradable_arb_count"].sum()) if not daily_fly.empty else 0
    mid_fly_count = int(daily_fly["violations_count_mid"].sum()) if not daily_fly.empty else 0
    lines.append(
        f"- Butterfly: {mid_fly_count} violations de convexité au mid, "
        f"{tradable_fly_count} violations exécutables au bid/ask sur les triplets adjacents."
    )
    if not best_coint.empty:
        row = best_coint.iloc[0]
        lines.append(
            f"- Meilleure paire co-intégrée: {row['product_a']} / {row['product_b']} "
            f"(tADF={row['adf_tstat']:.2f}, p≈{row['pvalue_approx']:.4f}, beta={row['beta']:.4f}, "
            f"EV≈{fmt(row['EV_par_trade'])} ticks/trade)."
        )
        if not best_coint_ev.empty:
            row_ev = best_coint_ev.iloc[0]
            lines.append(
                f"- Meilleure paire par EV net parmi les co-intégrées positives: {row_ev['product_a']} / {row_ev['product_b']} "
                f"(EV≈{fmt(row_ev['EV_par_trade'])} ticks/trade, p≈{row_ev['pvalue_approx']:.4f})."
            )
    if not best_synth.empty:
        row = best_synth.iloc[0]
        lines.append(
            f"- Synthétique VE: meilleur signal {row['product_a']} vs {row['product_b']} "
            f"avec edge max exécutable {fmt(row['max_tradable_edge'])} ticks."
        )
    lines.append("")

    lines.append("## Réponses aux 3 questions prioritaires")
    if tradable_fly_count > 0:
        row = best_fly[best_fly["tradable_arb_count"] > 0].iloc[0]
        lines.append(
            f"1. Violations butterfly persistantes: oui, meilleur cas exécutable "
            f"{row['product_a']}/{row['product_b']}/{row['product_c']} avec "
            f"{int(row['tradable_arb_count'])} timestamps et edge max {fmt(row['max_tradable_edge'])}."
        )
    elif mid_fly_count > 0:
        row = best_fly.iloc[0]
        lines.append(
            f"1. Violations butterfly persistantes: oui au mid, mais aucune ne survit au bid/ask. "
            f"Meilleur edge exécutable: {fmt(row['max_tradable_edge'])}."
        )
    else:
        lines.append("1. Violations butterfly persistantes: non. Aucune violation mid ni bid/ask détectée sur les triplets adjacents.")
    if not best_coint.empty:
        row = best_coint.iloc[0]
        ev_tail = ""
        if not best_coint_ev.empty:
            ev_tail = (
                f" La meilleure EV positive est {best_coint_ev.iloc[0]['product_a']} / {best_coint_ev.iloc[0]['product_b']} "
                f"à {fmt(best_coint_ev.iloc[0]['EV_par_trade'])} ticks/trade."
            )
        lines.append(
            f"2. Paires VEV: {row['product_a']} / {row['product_b']} est la plus robuste par p-value approx "
            f"(tADF={row['adf_tstat']:.2f}, p≈{row['pvalue_approx']:.4f}); EV net estimé "
            f"{fmt(row['EV_par_trade'])} ticks/trade.{ev_tail}"
        )
    else:
        lines.append("2. Paires VEV: aucune paire stationnaire exploitable détectée.")
    if not best_synth.empty:
        row = best_synth.iloc[0]
        beats = "oui" if row["tradable_arb_count"] > 0 else "non"
        lines.append(
            f"3. Réplication synthétique VE: {beats}. Le meilleur test est {row['type']} "
            f"({row['product_a']}), fréquence {fmt(row['opportunities_per_day'])}/jour, "
            f"edge max {fmt(row['max_tradable_edge'])}."
        )
    else:
        lines.append("3. Réplication synthétique VE: non détectée dans les coûts bid/ask.")
    lines.append("")

    lines.append("## Calls ou puts")
    min_corr = call_check["return_corr_vs_VE"].min()
    max_corr = call_check["return_corr_vs_VE"].max()
    lines.append(
        f"Les VEV se comportent comme des calls: les prix baissent avec le strike et les corrélations de returns "
        f"avec VE sont globalement positives ou nulles pour les options quasi mortes "
        f"(min={min_corr:.3f}, max={max_corr:.3f}). Pas de put caché détecté."
    )
    lines.append("")

    lines.append("## Top 5 actionnable")
    for rank, (_, row) in enumerate(top5.iterrows(), start=1):
        lines.append(
            f"{rank}. **{row['type']}** {row['product_a']} {row['product_b']} {row['product_c']} "
            f"- direction: {row['direction']}; EV={fmt(row['EV_par_trade'])}; "
            f"freq={fmt(row['opportunities_per_day'])}/jour; capital≈{fmt(row['capital_required_ticks'])}; "
            f"worst={fmt(row['risk_max_ticks'])}. {row['notes']}"
        )
    lines.append("")

    lines.append("## Pseudo-code des stratégies")
    lines.append("```python")
    lines.append("# 1) Butterfly convexity")
    lines.append("fly = w1*C[K1] - C[K2] + w3*C[K3]")
    lines.append("if zscore(fly) < -2 and entry_cost + exit_cost < expected_reversion:")
    lines.append("    buy(w1, C[K1]); sell(1, C[K2]); buy(w3, C[K3])")
    lines.append("if zscore(fly) > 0: close_all()")
    lines.append("")
    lines.append("# 2) Co-integration pair")
    lines.append("resid = C[K1] - beta*C[K2] - intercept")
    lines.append("if resid > mean + 2*std: sell(C[K1]); buy(beta, C[K2])")
    lines.append("if resid < mean: close_all()")
    lines.append("")
    lines.append("# 3) Synthetic VE")
    lines.append("synth = C[4000] + 4000")
    lines.append("if bid(VE) - ask(C[4000]) - 4000 > cost: buy(C[4000]); sell(VE)")
    lines.append("if abs(synth - VE) reverts through mean: close_all()")
    lines.append("")
    lines.append("# 4) HYD guard")
    lines.append("if rolling_corr(HYD, VE_or_VEV) < 0.3: do not pair HYD with VE complex")
    lines.append("")
    lines.append("# 5) Theta proxy")
    lines.append("theta_decay = C_prev - BS(S_prev, K, iv_prev, T_prev - 1/365)")
    lines.append("if realized_decay - theta_decay > spread: buy over-decayed call")
    lines.append("```")
    lines.append("")

    lines.append("## HYD pair-trade")
    strongest_hyd = hyd_corr.sort_values("max_abs_rolling_corr_250", ascending=False).head(5)
    lines.append(markdown_table(strongest_hyd))
    lines.append("")

    lines.append("## Theta proxy")
    theta_cols = ["product_a", "day_pair", "direction", "realized_decay", "bs_theta_decay", "edge_after_spread"]
    lines.append(markdown_table(theta[theta_cols].sort_values("edge_after_spread", ascending=False).head(12)))
    lines.append("")

    lines.append("## Meilleures p-values co-intégration")
    if not best_coint.empty:
        coint_cols = ["product_a", "product_b", "beta", "pvalue_approx", "EV_par_trade", "opportunities_per_day", "risk_max_ticks"]
        lines.append(markdown_table(best_coint[coint_cols].head(12)))
    lines.append("")

    lines.append("## Artefacts")
    lines.append("- `arb_opportunities.csv` : classement unique de toutes les opportunités.")
    lines.append("- `fly_daily_stats.csv` : table demandée par triplet et jour.")
    lines.append("- `fly_timeseries_by_triplet.png`")
    lines.append("- `correlation_matrix.png`")
    lines.append("- `synthetic_ve_vs_real.png`")
    lines.append("- `cointegration_pvalues_matrix.png`")
    lines.append("")

    lines.append("## Limitations")
    lines.append(
        "- Les p-values co-intégration sont une approximation ADF/Engle-Granger interne, suffisante pour classer les paires "
        "mais pas pour une inférence académique stricte."
    )
    lines.append(
        "- Les tests theta sont des proxys à partir de l'IV implicite estimée; la variation de spot peut dominer le theta pur."
    )
    lines.append(
        "- Les edges butterfly signalés au mid peuvent être du bid-ask bounce; le champ `tradable_arb_count` filtre les cas exécutables."
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def fmt(value: object) -> str:
    try:
        value_f = float(value)
    except Exception:
        return "n/a"
    if not np.isfinite(value_f):
        return "n/a"
    return f"{value_f:.3f}"


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Aucune ligne._"
    frame = df.copy()
    for col in frame.columns:
        frame[col] = frame[col].map(lambda x: fmt(x) if isinstance(x, (float, np.floating)) else str(x))
    headers = [str(c) for c in frame.columns]
    rows = frame.astype(str).values.tolist()
    widths = []
    for idx, header in enumerate(headers):
        max_cell = max([len(row[idx]) for row in rows] + [len(header)])
        widths.append(min(max_cell, 42))

    def clip(text: str, width: int) -> str:
        return text if len(text) <= width else text[: max(width - 1, 0)] + "…"

    out = []
    out.append("| " + " | ".join(clip(h, widths[i]).ljust(widths[i]) for i, h in enumerate(headers)) + " |")
    out.append("| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |")
    for row in rows:
        out.append("| " + " | ".join(clip(row[i], widths[i]).ljust(widths[i]) for i in range(len(headers))) + " |")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze R3 VE options spreads/stat arb.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent / "outputs")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prices = load_prices(args.data_dir)
    mid = build_wide(prices, "mid_price")
    bid = build_wide(prices, "bid_price_1")
    ask = build_wide(prices, "ask_price_1")
    half_spread = half_spread_from_wide(ask, bid)

    strikes = sorted(k for k in (strike_from_product(p) for p in mid.columns) if k is not None)

    call_check = confirm_calls(mid, strikes)
    daily_fly, fly_opps, fly_ts = analyze_flies(mid, bid, ask, half_spread, strikes)
    vertical_opps = analyze_vertical_pairs(mid, bid, ask, half_spread, strikes)
    theta = analyze_theta(mid, bid, ask, strikes)
    hyd_corr, corr = analyze_hyd_correlations(mid)
    synth_opps, synth_trace = analyze_synthetic(mid, bid, ask, half_spread, strikes)
    coint_opps, pvals = analyze_cointegration(mid, half_spread, strikes)

    # HYD rows are informational; only add if they show a candidate by the prompt threshold.
    hyd_opps_rows = []
    for _, row in hyd_corr[hyd_corr["pair_trade_candidate"]].iterrows():
        hyd_opps_rows.append(
            {
                "type": "hyd_pair_corr",
                "product_a": PRODUCT_HYD,
                "product_b": row["product"],
                "product_c": "",
                "K1": "",
                "K2": "",
                "K3": "",
                "direction": "pair trade only if event-driven correlation persists",
                "EV_par_trade": np.nan,
                "opportunities_per_day": np.nan,
                "capital_required_ticks": np.nan,
                "risk_max_ticks": np.nan,
                "frequency_count": np.nan,
                "tradable_arb_count": 0,
                "max_tradable_edge": np.nan,
                "score": -1.0,
                "notes": f"full_corr={row['return_corr_with_HYD']:.3f}, max_abs_roll250={row['max_abs_rolling_corr_250']:.3f}",
            }
        )
    hyd_opps = pd.DataFrame(hyd_opps_rows)

    all_opps = pd.concat(
        [fly_opps, vertical_opps, theta, synth_opps, coint_opps, hyd_opps],
        ignore_index=True,
        sort=False,
    )
    # Keep a stable, analyst-friendly column order.
    front_cols = [
        "type",
        "product_a",
        "product_b",
        "product_c",
        "K1",
        "K2",
        "K3",
        "direction",
        "EV_par_trade",
        "opportunities_per_day",
        "capital_required_ticks",
        "risk_max_ticks",
        "frequency_count",
        "tradable_arb_count",
        "max_tradable_edge",
        "score",
        "notes",
    ]
    ordered = front_cols + [c for c in all_opps.columns if c not in front_cols]
    all_opps = all_opps[ordered].sort_values(["score", "EV_par_trade"], ascending=False)

    all_opps.to_csv(args.output_dir / "arb_opportunities.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    daily_fly.to_csv(args.output_dir / "fly_daily_stats.csv", index=False)
    call_check.to_csv(args.output_dir / "call_confirmation.csv", index=False)
    hyd_corr.to_csv(args.output_dir / "hyd_correlations.csv", index=False)
    theta.to_csv(args.output_dir / "theta_proxy.csv", index=False)
    pvals.to_csv(args.output_dir / "cointegration_pvalues_matrix.csv")
    synth_trace.to_csv(args.output_dir / "synthetic_ve_trace.csv", index=False)

    plot_fly_timeseries(fly_ts, args.output_dir / "fly_timeseries_by_triplet.png")
    plot_heatmap(corr, args.output_dir / "correlation_matrix.png", "Return correlation matrix, 12 products", -1.0, 1.0)
    plot_synthetic_trace(synth_trace, args.output_dir / "synthetic_ve_vs_real.png")
    plot_heatmap(pvals, args.output_dir / "cointegration_pvalues_matrix.png", "Cointegration p-values, approx Engle-Granger", 0.0, 0.10, inverse=True)

    write_report(
        args.output_dir / "report.md",
        daily_fly=daily_fly,
        opportunities=all_opps,
        call_check=call_check,
        hyd_corr=hyd_corr,
        theta=theta,
        pvals=pvals,
        synth_trace=synth_trace,
    )

    print(f"Wrote outputs to {args.output_dir}")
    print("Top opportunities:")
    display_cols = ["type", "product_a", "product_b", "K1", "K2", "K3", "EV_par_trade", "opportunities_per_day", "score"]
    print(all_opps[display_cols].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
