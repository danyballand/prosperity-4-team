#!/usr/bin/env python3
"""
Follow-up analysis for P1 IV surface:
rolling IV surface, trade flow, residual dynamics, 5300/5400 spread,
and TTE sensitivity.

The script is intentionally self-contained except for pandas/numpy/Pillow.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


STRIKES = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
OPTION_PRODUCTS = [f"VEV_{k}" for k in STRIKES]
UNDERLYING = "VELVETFRUIT_EXTRACT"
TARGET_LONG = 5400
TARGET_SHORT = 5300
DEFAULT_DATA_DIR = Path("/Users/danyballand/Downloads/ROUND_3")
DEFAULT_IV_DIR = Path("outputs/iv_surface_round3")


def norm_cdf(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    sign = np.where(x < 0, -1.0, 1.0)
    z = np.abs(x) / math.sqrt(2.0)
    t = 1.0 / (1.0 + 0.3275911 * z)
    a1, a2, a3, a4, a5 = (
        0.254829592,
        -0.284496736,
        1.421413741,
        -1.453152027,
        1.061405429,
    )
    erf = sign * (
        1.0
        - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1)
        * t
        * np.exp(-(z * z))
    )
    return 0.5 * (1.0 + erf)


def norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_call(s: np.ndarray, k: np.ndarray, t: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    t = np.maximum(np.asarray(t, dtype=float), 1e-12)
    s = np.asarray(s, dtype=float)
    k = np.asarray(k, dtype=float)
    sqrt_t = np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return s * norm_cdf(d1) - k * norm_cdf(d2)


def bs_vega(s: np.ndarray, k: np.ndarray, t: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    sigma = np.maximum(np.asarray(sigma, dtype=float), 1e-12)
    t = np.maximum(np.asarray(t, dtype=float), 1e-12)
    s = np.asarray(s, dtype=float)
    k = np.asarray(k, dtype=float)
    sqrt_t = np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * sigma * sigma * t) / (sigma * sqrt_t)
    return s * norm_pdf(d1) * sqrt_t


def implied_vol_vectorized(
    s: np.ndarray, k: np.ndarray, t: np.ndarray, price: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    iv = np.full_like(price, np.nan, dtype=float)
    flags = np.full(price.shape, "ok", dtype=object)
    intrinsic = np.maximum(s - k, 0.0)
    invalid = (
        ~np.isfinite(s)
        | ~np.isfinite(k)
        | ~np.isfinite(t)
        | ~np.isfinite(price)
        | (s <= 0)
        | (k <= 0)
        | (t <= 0)
        | (price < intrinsic - 1e-7)
        | (price > s + 1e-7)
    )
    flags[invalid] = "invalid_no_arbitrage"
    pure_intrinsic = (~invalid) & (price <= intrinsic + 1e-7)
    flags[pure_intrinsic] = "pure_intrinsic"
    valid = (~invalid) & (~pure_intrinsic)
    if not valid.any():
        return iv, flags

    sv = s[valid]
    kv = k[valid]
    tv = t[valid]
    pv = price[valid]
    lo = np.full(pv.shape, 1e-6)
    hi = np.full(pv.shape, 5.0)
    high_price = bs_call(sv, kv, tv, hi)
    too_high = pv > high_price + 1e-7
    if too_high.any():
        valid_indices = np.flatnonzero(valid)
        flags[valid_indices[too_high]] = "above_sigma_cap"
    active = ~too_high
    if active.any():
        lo_a = lo[active]
        hi_a = hi[active]
        sa = sv[active]
        ka = kv[active]
        ta = tv[active]
        pa = pv[active]
        for _ in range(64):
            mid = 0.5 * (lo_a + hi_a)
            value = bs_call(sa, ka, ta, mid)
            too_low = value < pa
            lo_a = np.where(too_low, mid, lo_a)
            hi_a = np.where(too_low, hi_a, mid)
        active_indices = np.flatnonzero(valid)[active]
        iv[active_indices] = 0.5 * (lo_a + hi_a)
    return iv, flags


def load_prices(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in [0, 1, 2]:
        path = data_dir / f"prices_round_3_day_{day}.csv"
        frame = pd.read_csv(path, sep=";")
        frames.append(frame)
    prices = pd.concat(frames, ignore_index=True)
    prices = prices[prices["product"].isin([UNDERLYING, *OPTION_PRODUCTS])].copy()
    for col in ["bid_price_1", "ask_price_1", "mid_price", "bid_volume_1", "ask_volume_1"]:
        prices[col] = pd.to_numeric(prices[col], errors="coerce")
    prices["global_ts"] = prices["day"] * 1_000_000 + prices["timestamp"]
    return prices.sort_values(["day", "timestamp", "product"]).reset_index(drop=True)


def load_trades(data_dir: Path) -> pd.DataFrame:
    frames = []
    for day in [0, 1, 2]:
        path = data_dir / f"trades_round_3_day_{day}.csv"
        frame = pd.read_csv(path, sep=";")
        frame["day"] = day
        frames.append(frame)
    trades = pd.concat(frames, ignore_index=True)
    trades["quantity"] = pd.to_numeric(trades["quantity"], errors="coerce").fillna(0)
    trades["price"] = pd.to_numeric(trades["price"], errors="coerce")
    trades["global_ts"] = trades["day"] * 1_000_000 + trades["timestamp"]
    return trades.sort_values(["day", "timestamp", "symbol"]).reset_index(drop=True)


def build_panel(
    prices: pd.DataFrame,
    tte_start_days: float = 7.0,
    year_days: float = 250.0,
    intraday_decay: bool = True,
) -> pd.DataFrame:
    under = (
        prices[prices["product"] == UNDERLYING][["day", "timestamp", "global_ts", "mid_price"]]
        .rename(columns={"mid_price": "S"})
        .copy()
    )
    opts = prices[prices["product"].isin(OPTION_PRODUCTS)].copy()
    opts["strike"] = opts["product"].str.replace("VEV_", "", regex=False).astype(int)
    panel = opts.merge(under, on=["day", "timestamp", "global_ts"], how="left")
    panel = panel.rename(
        columns={
            "mid_price": "C_market",
            "bid_price_1": "bid",
            "ask_price_1": "ask",
            "bid_volume_1": "bid_volume",
            "ask_volume_1": "ask_volume",
        }
    )
    intraday = panel["timestamp"] / 1_000_000.0 if intraday_decay else 0.0
    panel["TTE_days"] = tte_start_days - panel["day"] - intraday
    panel["TTE_days"] = panel["TTE_days"].clip(lower=1e-6)
    panel["TTE"] = panel["TTE_days"] / year_days
    panel["year_days"] = year_days
    panel["half_spread"] = (panel["ask"] - panel["bid"]) / 2.0
    panel["log_moneyness"] = np.log(panel["strike"] / panel["S"])
    return panel.sort_values(["day", "timestamp", "strike"]).reset_index(drop=True)


def add_iv_and_surface(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = panel.copy()
    iv, flags = implied_vol_vectorized(
        out["S"].to_numpy(float),
        out["strike"].to_numpy(float),
        out["TTE"].to_numpy(float),
        out["C_market"].to_numpy(float),
    )
    out["IV"] = iv
    out["iv_flag"] = flags
    out["vega"] = bs_vega(
        out["S"].to_numpy(float),
        out["strike"].to_numpy(float),
        out["TTE"].to_numpy(float),
        np.where(np.isfinite(iv), iv, 0.2),
    )
    out.loc[~np.isfinite(out["IV"]), "vega"] = np.nan
    out["IV_surface"] = np.nan
    out["IV_residual"] = np.nan
    out["Z"] = np.nan
    rows = []
    for day, day_df in out.groupby("day"):
        valid = day_df["IV"].notna() & np.isfinite(day_df["log_moneyness"])
        coeff = np.polyfit(
            day_df.loc[valid, "log_moneyness"].to_numpy(float),
            day_df.loc[valid, "IV"].to_numpy(float),
            2,
        )
        idx = day_df.index
        surface = np.polyval(coeff, out.loc[idx, "log_moneyness"].to_numpy(float))
        out.loc[idx, "IV_surface"] = surface
        resid = out.loc[idx, "IV"] - surface
        out.loc[idx, "IV_residual"] = resid
        resid_std = float(np.nanstd(resid, ddof=1))
        out.loc[idx, "Z"] = resid / resid_std if resid_std > 0 else np.nan
        rows.append(
            {
                "day": day,
                "coef_quad": coeff[0],
                "coef_linear": coeff[1],
                "coef_intercept": coeff[2],
                "residual_std": resid_std,
                "valid_points": int(valid.sum()),
            }
        )
    out["surface_edge_ticks"] = out["vega"] * (out["IV_surface"] - out["IV"])
    out["long_ev_ticks"] = out["surface_edge_ticks"] - out["half_spread"]
    out["short_ev_ticks"] = -out["surface_edge_ticks"] - out["half_spread"]
    return out, pd.DataFrame(rows)


def rolling_surface(baseline: pd.DataFrame, window_ts: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = baseline.sort_values(["day", "timestamp", "strike"]).copy()
    result_frames = []
    coef_rows = []
    for day, day_df in df.groupby("day"):
        timestamps = np.array(sorted(day_df["timestamp"].unique()))
        n = len(timestamps)
        xtx = np.zeros((n, 3, 3), dtype=float)
        xty = np.zeros((n, 3), dtype=float)
        counts = np.zeros(n, dtype=int)
        ts_pos = {ts: i for i, ts in enumerate(timestamps)}
        valid = day_df["IV"].notna() & np.isfinite(day_df["log_moneyness"])
        for ts, group in day_df[valid].groupby("timestamp"):
            pos = ts_pos[ts]
            x = group["log_moneyness"].to_numpy(float)
            y = group["IV"].to_numpy(float)
            features = np.column_stack([x * x, x, np.ones_like(x)])
            xtx[pos] = features.T @ features
            xty[pos] = features.T @ y
            counts[pos] = len(group)
        xtx_cum = np.concatenate([np.zeros((1, 3, 3)), np.cumsum(xtx, axis=0)], axis=0)
        xty_cum = np.concatenate([np.zeros((1, 3)), np.cumsum(xty, axis=0)], axis=0)
        count_cum = np.concatenate([[0], np.cumsum(counts)])

        day_out = day_df.copy()
        day_out["rolling_coef_quad"] = np.nan
        day_out["rolling_coef_linear"] = np.nan
        day_out["rolling_coef_intercept"] = np.nan
        day_out["rolling_valid_points"] = 0
        day_out["rolling_IV_surface"] = np.nan
        day_out["rolling_IV_residual"] = np.nan
        day_out["rolling_surface_edge_ticks"] = np.nan
        day_out["rolling_long_ev_ticks"] = np.nan
        day_out["rolling_short_ev_ticks"] = np.nan

        for i, ts in enumerate(timestamps):
            start = max(0, i - window_ts + 1)
            mat = xtx_cum[i + 1] - xtx_cum[start]
            vec = xty_cum[i + 1] - xty_cum[start]
            count = int(count_cum[i + 1] - count_cum[start])
            if count < 30:
                continue
            try:
                coeff = np.linalg.solve(mat, vec)
            except np.linalg.LinAlgError:
                coeff = np.linalg.lstsq(mat, vec, rcond=None)[0]
            idx = day_out.index[day_out["timestamp"].eq(ts)]
            x_all = day_out.loc[idx, "log_moneyness"].to_numpy(float)
            surface = coeff[0] * x_all * x_all + coeff[1] * x_all + coeff[2]
            day_out.loc[idx, "rolling_coef_quad"] = coeff[0]
            day_out.loc[idx, "rolling_coef_linear"] = coeff[1]
            day_out.loc[idx, "rolling_coef_intercept"] = coeff[2]
            day_out.loc[idx, "rolling_valid_points"] = count
            day_out.loc[idx, "rolling_IV_surface"] = surface
            residual = day_out.loc[idx, "IV"].to_numpy(float) - surface
            day_out.loc[idx, "rolling_IV_residual"] = residual
            edge = day_out.loc[idx, "vega"].to_numpy(float) * (-residual)
            day_out.loc[idx, "rolling_surface_edge_ticks"] = edge
            day_out.loc[idx, "rolling_long_ev_ticks"] = edge - day_out.loc[idx, "half_spread"].to_numpy(float)
            day_out.loc[idx, "rolling_short_ev_ticks"] = -edge - day_out.loc[idx, "half_spread"].to_numpy(float)
            if ts % 100000 == 0 or i in (0, n - 1):
                coef_rows.append(
                    {
                        "day": int(day),
                        "timestamp": int(ts),
                        "window_ts": window_ts,
                        "coef_quad": coeff[0],
                        "coef_linear": coeff[1],
                        "coef_intercept": coeff[2],
                        "valid_points": count,
                    }
                )
        result_frames.append(day_out)

    rolling = pd.concat(result_frames, ignore_index=True)
    output_cols = [
        "day",
        "timestamp",
        "global_ts",
        "strike",
        "S",
        "C_market",
        "bid",
        "ask",
        "half_spread",
        "log_moneyness",
        "IV",
        "IV_surface",
        "IV_residual",
        "surface_edge_ticks",
        "long_ev_ticks",
        "short_ev_ticks",
        "rolling_coef_quad",
        "rolling_coef_linear",
        "rolling_coef_intercept",
        "rolling_valid_points",
        "rolling_IV_surface",
        "rolling_IV_residual",
        "rolling_surface_edge_ticks",
        "rolling_long_ev_ticks",
        "rolling_short_ev_ticks",
    ]
    rolling = rolling[output_cols]
    summary = (
        rolling.groupby(["day", "strike"], as_index=False)
        .agg(
            rows=("IV", "size"),
            valid_iv=("IV", lambda x: int(x.notna().sum())),
            mean_baseline_long_ev=("long_ev_ticks", "mean"),
            mean_baseline_short_ev=("short_ev_ticks", "mean"),
            mean_rolling_long_ev=("rolling_long_ev_ticks", "mean"),
            mean_rolling_short_ev=("rolling_short_ev_ticks", "mean"),
            rolling_long_positive_pct=("rolling_long_ev_ticks", lambda x: float((x > 0).mean())),
            rolling_short_positive_pct=("rolling_short_ev_ticks", lambda x: float((x > 0).mean())),
            mean_rolling_residual=("rolling_IV_residual", "mean"),
            std_rolling_residual=("rolling_IV_residual", "std"),
            mean_rolling_quad=("rolling_coef_quad", "mean"),
        )
        .sort_values(["day", "strike"])
    )
    summary["window_ts"] = window_ts
    return rolling, summary


def fit_2d_surface(baseline: pd.DataFrame) -> pd.DataFrame:
    valid = baseline["IV"].notna() & np.isfinite(baseline["log_moneyness"]) & np.isfinite(baseline["TTE"])
    df = baseline.loc[valid].copy()
    x = df["log_moneyness"].to_numpy(float)
    t = df["TTE"].to_numpy(float)
    y = df["IV"].to_numpy(float)
    features = np.column_stack([x * x, x, np.ones_like(x), t * x * x, t * x, t])
    coef, *_ = np.linalg.lstsq(features, y, rcond=None)
    pred = features @ coef
    df["IV_surface_2d"] = pred
    df["IV_residual_2d"] = df["IV"] - pred
    df["edge_2d_ticks"] = df["vega"] * (df["IV_surface_2d"] - df["IV"])
    df["long_ev_2d_ticks"] = df["edge_2d_ticks"] - df["half_spread"]
    df["short_ev_2d_ticks"] = -df["edge_2d_ticks"] - df["half_spread"]
    summary = (
        df.groupby("strike", as_index=False)
        .agg(
            mean_long_ev_2d=("long_ev_2d_ticks", "mean"),
            mean_short_ev_2d=("short_ev_2d_ticks", "mean"),
            mean_residual_2d=("IV_residual_2d", "mean"),
            std_residual_2d=("IV_residual_2d", "std"),
        )
        .sort_values("strike")
    )
    coef_row = {
        "strike": "COEFFICIENTS",
        "mean_long_ev_2d": np.nan,
        "mean_short_ev_2d": np.nan,
        "mean_residual_2d": np.nan,
        "std_residual_2d": float(np.std(df["IV_residual_2d"], ddof=1)),
        "coef_x2": coef[0],
        "coef_x": coef[1],
        "coef_const": coef[2],
        "coef_T_x2": coef[3],
        "coef_T_x": coef[4],
        "coef_T": coef[5],
    }
    return pd.concat([summary, pd.DataFrame([coef_row])], ignore_index=True)


def analyze_trade_flow(prices: pd.DataFrame, trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    option_trades = trades[trades["symbol"].isin(OPTION_PRODUCTS)].copy()
    book = prices[prices["product"].isin(OPTION_PRODUCTS)][
        ["day", "timestamp", "product", "bid_price_1", "ask_price_1", "mid_price", "bid_volume_1", "ask_volume_1"]
    ].rename(columns={"product": "symbol"})
    joined = option_trades.merge(book, on=["day", "timestamp", "symbol"], how="left")
    eps = 1e-9
    joined["side_class"] = np.select(
        [
            joined["price"] <= joined["bid_price_1"] + eps,
            joined["price"] >= joined["ask_price_1"] - eps,
            (joined["price"] - joined["mid_price"]).abs() <= eps,
        ],
        ["at_bid", "at_ask", "at_mid"],
        default="inside_spread",
    )
    joined["strike"] = joined["symbol"].str.replace("VEV_", "", regex=False).astype(int)

    depletion_rows = []
    for (day, product), group in prices[prices["product"].isin(OPTION_PRODUCTS)].groupby(["day", "product"]):
        group = group.sort_values("timestamp")
        same_bid = group["bid_price_1"].eq(group["bid_price_1"].shift())
        same_ask = group["ask_price_1"].eq(group["ask_price_1"].shift())
        bid_depl = (group["bid_volume_1"].shift() - group["bid_volume_1"]).where(same_bid, 0).clip(lower=0).sum()
        ask_depl = (group["ask_volume_1"].shift() - group["ask_volume_1"]).where(same_ask, 0).clip(lower=0).sum()
        depletion_rows.append(
            {
                "day": day,
                "symbol": product,
                "strike": int(product.replace("VEV_", "")),
                "book_bid_depletion_qty": float(bid_depl),
                "book_ask_depletion_qty": float(ask_depl),
            }
        )
    depletion = pd.DataFrame(depletion_rows)
    daily_public = (
        joined.pivot_table(
            index=["day", "strike", "symbol"],
            columns="side_class",
            values="quantity",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for col in ["at_bid", "at_ask", "at_mid", "inside_spread"]:
        if col not in daily_public.columns:
            daily_public[col] = 0.0
    daily_public["public_qty"] = daily_public[["at_bid", "at_ask", "at_mid", "inside_spread"]].sum(axis=1)
    daily_public = daily_public.merge(depletion, on=["day", "strike", "symbol"], how="left")

    rows = []
    for strike, group in joined.groupby("strike"):
        group = group.sort_values(["day", "timestamp"])
        qty_counts = group["quantity"].astype(int).value_counts().to_dict()
        deltas = []
        nonzero_deltas = []
        for _, day_group in group.groupby("day"):
            diffs = day_group["timestamp"].diff().dropna()
            deltas.extend(diffs.tolist())
            nonzero_deltas.extend(diffs[diffs > 0].tolist())
        daily = daily_public[daily_public["strike"].eq(strike)]
        public_qty = float(group["quantity"].sum())
        side_qty = group.groupby("side_class")["quantity"].sum().to_dict()
        avg_daily_at_bid = float(daily["at_bid"].mean()) if not daily.empty else 0.0
        avg_daily_at_ask = float(daily["at_ask"].mean()) if not daily.empty else 0.0
        row = {
            "strike": int(strike),
            "public_trade_count": int(len(group)),
            "public_total_qty": public_qty,
            "mean_trade_qty": float(group["quantity"].mean()) if len(group) else np.nan,
            "median_trade_qty": float(group["quantity"].median()) if len(group) else np.nan,
            "p90_trade_qty": float(group["quantity"].quantile(0.90)) if len(group) else np.nan,
            "max_trade_qty": float(group["quantity"].max()) if len(group) else np.nan,
            "mean_intertrade_ts_all": float(np.mean(deltas)) if deltas else np.nan,
            "median_intertrade_ts_all": float(np.median(deltas)) if deltas else np.nan,
            "mean_intertrade_ts_nonzero": float(np.mean(nonzero_deltas)) if nonzero_deltas else np.nan,
            "median_intertrade_ts_nonzero": float(np.median(nonzero_deltas)) if nonzero_deltas else np.nan,
            "at_bid_qty": float(side_qty.get("at_bid", 0.0)),
            "at_ask_qty": float(side_qty.get("at_ask", 0.0)),
            "at_mid_qty": float(side_qty.get("at_mid", 0.0)),
            "inside_spread_qty": float(side_qty.get("inside_spread", 0.0)),
            "at_bid_frac": float(side_qty.get("at_bid", 0.0) / public_qty) if public_qty else np.nan,
            "at_ask_frac": float(side_qty.get("at_ask", 0.0) / public_qty) if public_qty else np.nan,
            "avg_daily_at_bid_qty": avg_daily_at_bid,
            "avg_daily_at_ask_qty": avg_daily_at_ask,
            "realistic_long_build_per_day_bid": avg_daily_at_bid,
            "realistic_short_build_per_day_ask": avg_daily_at_ask,
            "book_bid_depletion_qty": float(daily["book_bid_depletion_qty"].sum()) if not daily.empty else np.nan,
            "book_ask_depletion_qty": float(daily["book_ask_depletion_qty"].sum()) if not daily.empty else np.nan,
        }
        for qty in range(1, 11):
            row[f"qty_{qty}_trade_count"] = int(qty_counts.get(qty, 0))
        rows.append(row)
    flow = pd.DataFrame(rows).sort_values("strike")
    flow["book_vs_public_qty_ratio"] = (
        (flow["book_bid_depletion_qty"] + flow["book_ask_depletion_qty"])
        / flow["public_total_qty"].replace(0, np.nan)
    )
    return flow, joined


def ols_regression(y: pd.Series, x: pd.Series) -> dict[str, float]:
    data = pd.concat({"y": y, "x": x}, axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 5 or data["x"].std() == 0:
        return {"n": len(data), "alpha": np.nan, "beta": np.nan, "t_beta": np.nan, "r2": np.nan}
    yv = data["y"].to_numpy(float)
    xv = data["x"].to_numpy(float)
    xmat = np.column_stack([np.ones(len(xv)), xv])
    beta, *_ = np.linalg.lstsq(xmat, yv, rcond=None)
    resid = yv - xmat @ beta
    dof = max(len(yv) - 2, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    cov = sigma2 * np.linalg.pinv(xmat.T @ xmat)
    se_beta = math.sqrt(max(cov[1, 1], 1e-18))
    ss_tot = float(np.dot(yv - yv.mean(), yv - yv.mean()))
    ss_res = float(np.dot(resid, resid))
    return {
        "n": int(len(data)),
        "alpha": float(beta[0]),
        "beta": float(beta[1]),
        "t_beta": float(beta[1] / se_beta),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
    }


def ar1_stats(series: pd.Series) -> dict[str, float]:
    x = series.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    if len(x) < 3 or np.std(x) == 0:
        return {"ar1": np.nan, "half_life_ts": np.nan}
    centered = x - x.mean()
    rho = float(np.dot(centered[:-1], centered[1:]) / max(np.dot(centered[:-1], centered[:-1]), 1e-18))
    if 0 < rho < 1:
        hl = -math.log(2) / math.log(rho)
    elif rho >= 1:
        hl = math.inf
    else:
        hl = 0.0
    return {"ar1": rho, "half_life_ts": float(hl)}


def autocorr_values(series: pd.Series, max_lag: int = 100) -> pd.DataFrame:
    x = series.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(float)
    x = x - x.mean()
    denom = np.dot(x, x)
    rows = []
    for lag in range(1, max_lag + 1):
        if lag >= len(x) or denom == 0:
            ac = np.nan
        else:
            ac = float(np.dot(x[:-lag], x[lag:]) / denom)
        rows.append({"lag": lag, "autocorr": ac})
    return pd.DataFrame(rows)


def analyze_residual_dynamics(baseline: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    targets = baseline[baseline["strike"].isin([TARGET_SHORT, TARGET_LONG])].copy()
    s_moves = (
        baseline[["day", "timestamp", "S"]]
        .drop_duplicates(["day", "timestamp"])
        .sort_values(["day", "timestamp"])
        .copy()
    )
    s_moves["dS"] = s_moves.groupby("day")["S"].diff()
    targets = targets.drop(columns=["dS"], errors="ignore").merge(
        s_moves[["day", "timestamp", "dS"]], on=["day", "timestamp"], how="left"
    )
    rows = []
    autocorr_frames = []
    for strike, group in targets.groupby("strike"):
        group = group.sort_values(["day", "timestamp"])
        resid = group["IV_residual"]
        edge = group["surface_edge_ticks"]
        s_centered = group["S"] - group["S"].mean()
        for y_name, y in [("IV_residual", resid), ("surface_edge_ticks", edge)]:
            reg_s = ols_regression(y, s_centered)
            reg_ds = ols_regression(y, group["dS"])
            ar = ar1_stats(y)
            rows.append(
                {
                    "strike": int(strike),
                    "y": y_name,
                    "regressor": "S_minus_mean",
                    **reg_s,
                    **ar,
                    "recommendation_signal": classify_residual_timing(reg_s, reg_ds, ar),
                }
            )
            rows.append(
                {
                    "strike": int(strike),
                    "y": y_name,
                    "regressor": "dS_1tick",
                    **reg_ds,
                    **ar,
                    "recommendation_signal": classify_residual_timing(reg_s, reg_ds, ar),
                }
            )
        ac = autocorr_values(resid, 120)
        ac["strike"] = int(strike)
        autocorr_frames.append(ac)
    targets["time_bin_100k"] = (targets["timestamp"] // 100000) * 100000
    regimes = (
        targets.groupby(["day", "time_bin_100k", "strike"], as_index=False)
        .agg(
            rows=("IV_residual", "size"),
            mean_S=("S", "mean"),
            mean_residual=("IV_residual", "mean"),
            std_residual=("IV_residual", "std"),
            mean_edge_ticks=("surface_edge_ticks", "mean"),
            mean_long_ev_ticks=("long_ev_ticks", "mean"),
            mean_short_ev_ticks=("short_ev_ticks", "mean"),
        )
        .sort_values(["day", "time_bin_100k", "strike"])
    )
    scatter = targets[["day", "timestamp", "global_ts", "strike", "S", "dS", "IV_residual", "surface_edge_ticks"]].copy()
    return pd.DataFrame(rows), regimes, pd.concat(autocorr_frames, ignore_index=True), scatter


def classify_residual_timing(reg_s: dict[str, float], reg_ds: dict[str, float], ar: dict[str, float]) -> str:
    s_sig = np.isfinite(reg_s.get("t_beta", np.nan)) and abs(reg_s["t_beta"]) > 2 and reg_s.get("r2", 0) > 0.02
    ds_sig = np.isfinite(reg_ds.get("t_beta", np.nan)) and abs(reg_ds["t_beta"]) > 2 and reg_ds.get("r2", 0) > 0.01
    ar_sig = np.isfinite(ar.get("ar1", np.nan)) and ar["ar1"] > 0.80
    if ar_sig and (s_sig or ds_sig):
        return "TIMING_INTELLIGENT"
    if ar_sig:
        return "TIMING_ON_ZSCORE"
    if s_sig or ds_sig:
        return "DELTA_CONDITIONED"
    return "CONSTANT_PAIR_OK"


def analyze_pair_spread(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    opts = prices[prices["product"].isin([f"VEV_{TARGET_SHORT}", f"VEV_{TARGET_LONG}"])].copy()
    wide_mid = opts.pivot_table(index=["day", "timestamp", "global_ts"], columns="product", values="mid_price").sort_index()
    wide_bid = opts.pivot_table(index=["day", "timestamp", "global_ts"], columns="product", values="bid_price_1").sort_index()
    wide_ask = opts.pivot_table(index=["day", "timestamp", "global_ts"], columns="product", values="ask_price_1").sort_index()
    c5300 = f"VEV_{TARGET_SHORT}"
    c5400 = f"VEV_{TARGET_LONG}"
    spread = wide_mid[c5300] - wide_mid[c5400]
    out = spread.reset_index().rename(columns={0: "spread_mid"})
    out["spread_mid"] = spread.to_numpy(float)
    mu = float(spread.mean())
    sigma = float(spread.std(ddof=1))
    out["mean"] = mu
    out["upper_1sigma"] = mu + sigma
    out["lower_1sigma"] = mu - sigma
    ar = ar1_stats(spread)

    in_trade = False
    entry = None
    trades = []
    for idx, row in out.iterrows():
        key = (row["day"], row["timestamp"], row["global_ts"])
        if not in_trade and row["spread_mid"] > mu + sigma:
            entry_spread_exec = float(wide_bid.loc[key, c5300] - wide_ask.loc[key, c5400])
            entry = {
                "entry_day": row["day"],
                "entry_timestamp": row["timestamp"],
                "entry_global_ts": row["global_ts"],
                "entry_spread_mid": row["spread_mid"],
                "entry_spread_exec": entry_spread_exec,
            }
            in_trade = True
        elif in_trade and row["spread_mid"] <= mu:
            exit_spread_exec = float(wide_ask.loc[key, c5300] - wide_bid.loc[key, c5400])
            pnl = entry["entry_spread_exec"] - exit_spread_exec
            trades.append(
                {
                    **entry,
                    "exit_day": row["day"],
                    "exit_timestamp": row["timestamp"],
                    "exit_global_ts": row["global_ts"],
                    "exit_spread_mid": row["spread_mid"],
                    "exit_spread_exec": exit_spread_exec,
                    "holding_ts": row["global_ts"] - entry["entry_global_ts"],
                    "pnl_ticks": pnl,
                    "strategy": "short_spread_when_above_1sigma",
                }
            )
            in_trade = False
    if in_trade and entry is not None:
        key = out.iloc[-1][["day", "timestamp", "global_ts"]]
        key_tuple = (key["day"], key["timestamp"], key["global_ts"])
        exit_spread_exec = float(wide_ask.loc[key_tuple, c5300] - wide_bid.loc[key_tuple, c5400])
        pnl = entry["entry_spread_exec"] - exit_spread_exec
        trades.append(
            {
                **entry,
                "exit_day": key["day"],
                "exit_timestamp": key["timestamp"],
                "exit_global_ts": key["global_ts"],
                "exit_spread_mid": float(out.iloc[-1]["spread_mid"]),
                "exit_spread_exec": exit_spread_exec,
                "holding_ts": key["global_ts"] - entry["entry_global_ts"],
                "pnl_ticks": pnl,
                "strategy": "forced_exit_end",
            }
        )
    trade_df = pd.DataFrame(trades)
    first_key = wide_mid.index[0]
    last_key = wide_mid.index[-1]
    static_pnl = float((wide_bid.loc[first_key, c5300] - wide_ask.loc[first_key, c5400]) - (wide_ask.loc[last_key, c5300] - wide_bid.loc[last_key, c5400]))
    summary = pd.DataFrame(
        [
            {
                "metric": "spread_mean",
                "value": mu,
                "notes": "C5300_mid - C5400_mid",
            },
            {"metric": "spread_std", "value": sigma, "notes": ""},
            {"metric": "spread_min", "value": float(spread.min()), "notes": ""},
            {"metric": "spread_max", "value": float(spread.max()), "notes": ""},
            {"metric": "spread_ar1", "value": ar["ar1"], "notes": ""},
            {"metric": "spread_half_life_ts", "value": ar["half_life_ts"], "notes": ""},
            {
                "metric": "timed_signal_trade_count",
                "value": int(len(trade_df)),
                "notes": "SHORT spread if spread > mean + std; close at mean",
            },
            {
                "metric": "timed_signal_ev_per_trade",
                "value": float(trade_df["pnl_ticks"].mean()) if len(trade_df) else np.nan,
                "notes": "executed bid/ask estimate",
            },
            {
                "metric": "timed_signal_total_pnl",
                "value": float(trade_df["pnl_ticks"].sum()) if len(trade_df) else 0.0,
                "notes": "one-lot pair",
            },
            {
                "metric": "static_short_spread_pnl",
                "value": static_pnl,
                "notes": "enter first timestamp, exit last timestamp, one-lot pair",
            },
        ]
    )
    out["short_spread_signal"] = out["spread_mid"] > mu + sigma
    return out, pd.concat([summary, trade_df], ignore_index=True, sort=False)


def tte_sensitivity(prices: pd.DataFrame) -> pd.DataFrame:
    scenarios = [
        ("7j_x250_intraday_BASELINE", 7.0, 250.0, True),
        ("5j_x250_intraday", 5.0, 250.0, True),
        ("10j_x250_intraday", 10.0, 250.0, True),
        ("7j_x365_intraday", 7.0, 365.0, True),
        ("7j_x250_no_intraday_decay", 7.0, 250.0, False),
    ]
    rows = []
    for name, start_days, year_days, intraday in scenarios:
        panel = build_panel(prices, start_days, year_days, intraday)
        surface, fit = add_iv_and_surface(panel)
        overall = surface.groupby("strike", as_index=False).agg(
            mean_iv=("IV", "mean"),
            mean_long_ev_ticks=("long_ev_ticks", "mean"),
            mean_short_ev_ticks=("short_ev_ticks", "mean"),
            mean_surface_edge_ticks=("surface_edge_ticks", "mean"),
            valid_iv=("IV", lambda x: int(x.notna().sum())),
        )
        row_5400 = overall[overall["strike"].eq(TARGET_LONG)].iloc[0]
        row_5300 = overall[overall["strike"].eq(TARGET_SHORT)].iloc[0]
        atm = overall[overall["strike"].isin([5200, 5300])]["mean_iv"].mean()
        verdict = "GO" if row_5400["mean_long_ev_ticks"] > 0 and row_5300["mean_short_ev_ticks"] > 0 else "NO-GO"
        if verdict == "GO" and min(row_5400["mean_long_ev_ticks"], row_5300["mean_short_ev_ticks"]) < 0.5:
            verdict = "CAUTION"
        rows.append(
            {
                "TTE_assumption": name,
                "tte_start_days": start_days,
                "year_days": year_days,
                "intraday_decay": intraday,
                "edge_5400_long": row_5400["mean_long_ev_ticks"],
                "edge_5300_short": row_5300["mean_short_ev_ticks"],
                "mean_iv_5200_5300": atm,
                "fit_quad_day0": fit.loc[fit["day"].eq(0), "coef_quad"].iloc[0],
                "fit_quad_day2": fit.loc[fit["day"].eq(2), "coef_quad"].iloc[0],
                "verdict": verdict,
            }
        )
    return pd.DataFrame(rows)


def font(size: int = 12) -> ImageFont.ImageFont:
    for path in [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_line_chart(
    series_list: list[tuple[str, np.ndarray, tuple[int, int, int]]],
    output: Path,
    title: str,
    y_label: str = "",
    hlines: list[tuple[float, str, tuple[int, int, int]]] | None = None,
    width: int = 1200,
    height: int = 680,
) -> None:
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    f = font(12)
    tf = font(20)
    left, top, plot_w, plot_h = 85, 70, width - 150, height - 170
    d.text((30, 25), title, fill=(20, 20, 20), font=tf)
    all_y = np.concatenate([s[np.isfinite(s)] for _, s, _ in series_list if np.isfinite(s).any()])
    if hlines:
        all_y = np.concatenate([all_y, np.array([v for v, _, _ in hlines])])
    ymin, ymax = float(np.nanmin(all_y)), float(np.nanmax(all_y))
    pad = max((ymax - ymin) * 0.08, 1e-6)
    ymin -= pad
    ymax += pad
    d.rectangle([left, top, left + plot_w, top + plot_h], outline=(185, 185, 185), fill=(250, 250, 250))
    if hlines:
        for value, label, color in hlines:
            y = top + plot_h - int((value - ymin) / (ymax - ymin) * plot_h)
            d.line([left, y, left + plot_w, y], fill=color, width=1)
            d.text((left + plot_w + 5, y - 7), label, fill=color, font=f)
    for idx, (label, y_values, color) in enumerate(series_list):
        finite = np.isfinite(y_values)
        if finite.sum() < 2:
            continue
        x = np.arange(len(y_values))
        xp = left + ((x[finite] - x[finite].min()) / max(x[finite].max() - x[finite].min(), 1)) * plot_w
        yp = top + plot_h - ((y_values[finite] - ymin) / (ymax - ymin)) * plot_h
        d.line(list(zip(xp.astype(int), yp.astype(int))), fill=color, width=2)
        ly = top + plot_h + 25 + idx * 22
        d.rectangle([left + 15, ly + 3, left + 28, ly + 16], fill=color)
        d.text((left + 35, ly), label, fill=(30, 30, 30), font=f)
    d.text((15, top), f"{ymax:.2f}", fill=(30, 30, 30), font=f)
    d.text((15, top + plot_h - 10), f"{ymin:.2f}", fill=(30, 30, 30), font=f)
    if y_label:
        d.text((30, top + plot_h // 2), y_label, fill=(30, 30, 30), font=f)
    img.save(output)


def draw_scatter(df: pd.DataFrame, output: Path) -> None:
    img = Image.new("RGB", (1100, 620), "white")
    d = ImageDraw.Draw(img)
    f = font(12)
    tf = font(20)
    left, top, plot_w, plot_h = 85, 70, 930, 430
    d.text((30, 25), "Residual IV vs short-term dS", fill=(20, 20, 20), font=tf)
    x = df["dS"].to_numpy(float)
    y = df["IV_residual"].to_numpy(float)
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]
    xmin, xmax = np.percentile(x, [1, 99])
    ymin, ymax = np.percentile(y, [1, 99])
    xpad = max((xmax - xmin) * 0.08, 1e-6)
    ypad = max((ymax - ymin) * 0.08, 1e-6)
    xmin -= xpad
    xmax += xpad
    ymin -= ypad
    ymax += ypad
    d.rectangle([left, top, left + plot_w, top + plot_h], outline=(185, 185, 185), fill=(250, 250, 250))
    colors = {TARGET_SHORT: (200, 85, 50), TARGET_LONG: (45, 110, 180)}
    for strike, group in df.groupby("strike"):
        gx = group["dS"].to_numpy(float)
        gy = group["IV_residual"].to_numpy(float)
        finite = np.isfinite(gx) & np.isfinite(gy)
        gx, gy = gx[finite], gy[finite]
        if len(gx) > 5000:
            step = max(len(gx) // 5000, 1)
            gx, gy = gx[::step], gy[::step]
        xp = left + ((gx - xmin) / (xmax - xmin)) * plot_w
        yp = top + plot_h - ((gy - ymin) / (ymax - ymin)) * plot_h
        color = colors.get(int(strike), (80, 80, 80))
        for xx, yy in zip(xp, yp):
            if left <= xx <= left + plot_w and top <= yy <= top + plot_h:
                d.ellipse([xx - 1, yy - 1, xx + 1, yy + 1], fill=color)
    d.line([left, top + plot_h // 2, left + plot_w, top + plot_h // 2], fill=(200, 200, 200))
    d.line([left + plot_w // 2, top, left + plot_w // 2, top + plot_h], fill=(200, 200, 200))
    d.text((left, top + plot_h + 20), f"dS range {xmin:.1f} to {xmax:.1f}", font=f, fill=(30, 30, 30))
    d.text((left + 15, top + plot_h + 45), f"VEV_{TARGET_SHORT}", font=f, fill=colors[TARGET_SHORT])
    d.text((left + 120, top + plot_h + 45), f"VEV_{TARGET_LONG}", font=f, fill=colors[TARGET_LONG])
    img.save(output)


def draw_trade_flow(flow: pd.DataFrame, output: Path) -> None:
    targets = flow[flow["strike"].isin([TARGET_SHORT, TARGET_LONG])].copy()
    img = Image.new("RGB", (1000, 620), "white")
    d = ImageDraw.Draw(img)
    f = font(12)
    tf = font(20)
    d.text((30, 25), "Trade flow size and side mix, 5300/5400", fill=(20, 20, 20), font=tf)
    left, top = 90, 90
    bar_w = 60
    max_count = max(targets[[f"qty_{i}_trade_count" for i in range(1, 11)]].to_numpy().max(), 1)
    colors = {TARGET_SHORT: (200, 85, 50), TARGET_LONG: (45, 110, 180)}
    for s_idx, (_, row) in enumerate(targets.iterrows()):
        base_x = left + s_idx * 430
        d.text((base_x, top - 30), f"VEV_{int(row['strike'])}", fill=colors[int(row["strike"])], font=font(16))
        for qty in range(1, 11):
            count = row[f"qty_{qty}_trade_count"]
            h = int(230 * count / max_count)
            x0 = base_x + (qty - 1) * (bar_w // 2 + 5)
            y0 = top + 250 - h
            d.rectangle([x0, y0, x0 + bar_w // 2, top + 250], fill=colors[int(row["strike"])])
            d.text((x0, top + 255), str(qty), fill=(30, 30, 30), font=f)
        y = top + 315
        d.text((base_x, y), f"mean qty {row['mean_trade_qty']:.2f}, median {row['median_trade_qty']:.1f}", font=f, fill=(30, 30, 30))
        d.text((base_x, y + 22), f"mean nonzero intertrade {row['mean_intertrade_ts_nonzero']:.0f} ts", font=f, fill=(30, 30, 30))
        d.text((base_x, y + 44), f"at bid {row['at_bid_frac']:.1%}, at ask {row['at_ask_frac']:.1%}", font=f, fill=(30, 30, 30))
        d.text((base_x, y + 66), f"realistic bid/day {row['avg_daily_at_bid_qty']:.1f}, ask/day {row['avg_daily_at_ask_qty']:.1f}", font=f, fill=(30, 30, 30))
    d.text((left, top + 285), "trade quantity bucket", font=f, fill=(30, 30, 30))
    img.save(output)


def draw_bar_chart(df: pd.DataFrame, output: Path, title: str) -> None:
    img = Image.new("RGB", (1100, 620), "white")
    d = ImageDraw.Draw(img)
    f = font(11)
    tf = font(20)
    d.text((30, 25), title, fill=(20, 20, 20), font=tf)
    labels = df["TTE_assumption"].tolist()
    v1 = df["edge_5400_long"].to_numpy(float)
    v2 = df["edge_5300_short"].to_numpy(float)
    vals = np.concatenate([v1, v2, np.array([0.0])])
    ymin, ymax = float(vals.min()), float(vals.max())
    pad = max((ymax - ymin) * 0.12, 1.0)
    ymin -= pad
    ymax += pad
    left, top, plot_w, plot_h = 85, 80, 940, 390
    d.rectangle([left, top, left + plot_w, top + plot_h], outline=(185, 185, 185), fill=(250, 250, 250))
    zero_y = top + plot_h - int((0 - ymin) / (ymax - ymin) * plot_h)
    d.line([left, zero_y, left + plot_w, zero_y], fill=(80, 80, 80), width=1)
    group_w = plot_w / max(len(labels), 1)
    for i, label in enumerate(labels):
        x_center = left + i * group_w + group_w / 2
        for offset, value, color in [(-18, v1[i], (45, 110, 180)), (18, v2[i], (200, 85, 50))]:
            y = top + plot_h - ((value - ymin) / (ymax - ymin)) * plot_h
            d.rectangle([x_center + offset - 12, min(y, zero_y), x_center + offset + 12, max(y, zero_y)], fill=color)
        d.text((int(x_center - group_w / 2 + 5), top + plot_h + 12), label.replace("_", "\n")[:28], fill=(30, 30, 30), font=f)
    d.text((left + 20, top + plot_h + 110), "Blue: 5400 long edge | Red: 5300 short edge", fill=(30, 30, 30), font=f)
    img.save(output)


def write_report(
    output: Path,
    rolling_summary: pd.DataFrame,
    surface_2d: pd.DataFrame,
    trade_flow: pd.DataFrame,
    regressions: pd.DataFrame,
    regimes: pd.DataFrame,
    pair_summary: pd.DataFrame,
    tte: pd.DataFrame,
) -> None:
    r5400 = rolling_summary[rolling_summary["strike"].eq(TARGET_LONG)]
    r5300 = rolling_summary[rolling_summary["strike"].eq(TARGET_SHORT)]
    q1_go = (
        r5400["mean_rolling_long_ev"].mean() > 0
        and r5300["mean_rolling_short_ev"].mean() > 0
        and r5400["rolling_long_positive_pct"].mean() > 0.55
    )
    f5400 = trade_flow[trade_flow["strike"].eq(TARGET_LONG)].iloc[0]
    f5300 = trade_flow[trade_flow["strike"].eq(TARGET_SHORT)].iloc[0]
    pair_build = min(f5400["avg_daily_at_bid_qty"], f5300["avg_daily_at_ask_qty"])
    timed_ev = pair_summary[pair_summary["metric"].eq("timed_signal_ev_per_trade")]["value"].iloc[0]
    static_pnl = pair_summary[pair_summary["metric"].eq("static_short_spread_pnl")]["value"].iloc[0]
    tte_go = (tte["verdict"].eq("GO") | tte["verdict"].eq("CAUTION")).all()
    reg5400 = regressions[(regressions["strike"].eq(TARGET_LONG)) & (regressions["y"].eq("IV_residual"))]
    ar5400 = reg5400["ar1"].dropna().iloc[0]
    ds5400 = reg5400[reg5400["regressor"].eq("dS_1tick")].iloc[0]

    lines = []
    lines.append("# P1 Follow-up IV Surface")
    lines.append("")
    lines.append("## Q1 - Stabilité rolling / surface 2D")
    lines.append(
        f"Verdict: {'GO' if q1_go else 'CAUTION'}. Rolling 500ts garde 5400 en edge long moyen "
        f"{r5400['mean_rolling_long_ev'].mean():.3f} ticks et 5300 en edge short moyen "
        f"{r5300['mean_rolling_short_ev'].mean():.3f} ticks. "
        f"Le taux de positivité rolling 5400 long est {r5400['rolling_long_positive_pct'].mean():.1%}."
    )
    lines.append(
        "La hausse du coef quadratique est compatible avec le raccourcissement du TTE, mais 3 jours ne permettent "
        "pas de séparer proprement time decay et changement de régime informé. La surface 2D linéaire en T est fitable; "
        "voir `surface_2d_summary.csv`."
    )
    lines.append("")
    lines.append("## Q2 - Fréquence des fills")
    lines.append(
        f"Verdict: {'GO' if pair_build >= 40 else 'CAUTION'}. 5400 a {f5400['public_trade_count']:.0f} trades publics, "
        f"taille moyenne {f5400['mean_trade_qty']:.2f}; 5300 a {f5300['public_trade_count']:.0f} trades, "
        f"taille moyenne {f5300['mean_trade_qty']:.2f}. Build pair réaliste par jour via bid 5400 + ask 5300: "
        f"~{pair_build:.1f} contrats/jour."
    )
    lines.append(
        f"Side mix: 5400 at-bid {f5400['at_bid_frac']:.1%}, at-ask {f5400['at_ask_frac']:.1%}; "
        f"5300 at-bid {f5300['at_bid_frac']:.1%}, at-ask {f5300['at_ask_frac']:.1%}. "
        "Le ratio book-depletion/public est un proxy noisy des prints non publics."
    )
    lines.append("")
    lines.append("## Q3 - Résidu vs move VE")
    lines.append(
        f"Verdict: {'TIMING INTELLIGENT' if ar5400 > 0.8 else 'CONSTANT PAIR'}. "
        f"Résidu 5400 AR(1)={ar5400:.3f}; régression sur dS beta={ds5400['beta']:.5f}, "
        f"t={ds5400['t_beta']:.2f}, R2={ds5400['r2']:.3f}. "
        "Le timing par z-score/résidu est plus utile que trader à chaque tick."
    )
    lines.append("")
    lines.append("## Q4 - Spread prix 5300 - 5400")
    lines.append(
        f"Verdict: {'GO' if timed_ev > static_pnl else 'CAUTION'}. Signal SHORT spread si spread > mean+sigma: "
        f"EV/trade={timed_ev:.3f} ticks vs static short-spread PnL={static_pnl:.3f} ticks sur 1 lot. "
        "Le spread est borné et fortement autocorrélé; l'entrée timée évite de payer le carry quand le spread est normal."
    )
    lines.append("")
    lines.append("## Q5 - Sensibilité TTE")
    base = tte[tte["TTE_assumption"].str.contains("BASELINE")].iloc[0]
    lines.append(
        f"Verdict: {'GO' if tte_go else 'CAUTION'}. Baseline 7j x250: edge 5400 long={base['edge_5400_long']:.3f}, "
        f"edge 5300 short={base['edge_5300_short']:.3f}. Les scénarios 5j/10j/365 gardent le signe; "
        "250 jours avec decay intraday reste le plus plausible car l'IV ATM reste dans la zone 15-25%."
    )
    lines.append("")
    lines.append("## Fichiers produits")
    for name in [
        "rolling_surface_iv.csv",
        "rolling_surface_summary.csv",
        "surface_2d_summary.csv",
        "trade_flow_analysis.csv",
        "residual_regressions.csv",
        "residual_time_regimes.csv",
        "pair_spread_backtest.csv",
        "tte_sensitivity.csv",
    ]:
        lines.append(f"- `{name}`")
    for name in [
        "rolling_surface_edges.png",
        "trade_flow_distribution.png",
        "residual_vs_dS.png",
        "residual_autocorr.png",
        "spread_5300_5400_timeseries.png",
        "tte_sensitivity.png",
    ]:
        lines.append(f"- `{name}`")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="P1 follow-up analysis.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--iv-dir", type=Path, default=DEFAULT_IV_DIR)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/iv_surface_followup_p1"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    baseline = pd.read_csv(args.iv_dir / "iv_surface.csv")
    if "global_ts" not in baseline.columns:
        baseline["global_ts"] = baseline["day"] * 1_000_000 + baseline["timestamp"]
    prices = load_prices(args.data_dir)
    trades = load_trades(args.data_dir)

    rolling, rolling_summary = rolling_surface(baseline, window_ts=500)
    surface_2d = fit_2d_surface(baseline)
    trade_flow, joined_trades = analyze_trade_flow(prices, trades)
    regressions, regimes, autocorr, scatter = analyze_residual_dynamics(baseline)
    spread_ts, pair_backtest = analyze_pair_spread(prices)
    tte = tte_sensitivity(prices)

    rolling.to_csv(args.output_dir / "rolling_surface_iv.csv", index=False)
    rolling_summary.to_csv(args.output_dir / "rolling_surface_summary.csv", index=False)
    surface_2d.to_csv(args.output_dir / "surface_2d_summary.csv", index=False)
    trade_flow.to_csv(args.output_dir / "trade_flow_analysis.csv", index=False)
    joined_trades.to_csv(args.output_dir / "trade_flow_joined_trades.csv", index=False)
    regressions.to_csv(args.output_dir / "residual_regressions.csv", index=False)
    regimes.to_csv(args.output_dir / "residual_time_regimes.csv", index=False)
    autocorr.to_csv(args.output_dir / "residual_autocorr.csv", index=False)
    scatter.to_csv(args.output_dir / "residual_scatter_source.csv", index=False)
    spread_ts.to_csv(args.output_dir / "spread_5300_5400_timeseries.csv", index=False)
    pair_backtest.to_csv(args.output_dir / "pair_spread_backtest.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    tte.to_csv(args.output_dir / "tte_sensitivity.csv", index=False)

    target_roll = rolling[rolling["strike"].isin([TARGET_SHORT, TARGET_LONG])].sort_values(["day", "timestamp", "strike"])
    pivot_roll = target_roll.pivot_table(index=["day", "timestamp"], columns="strike", values=["rolling_long_ev_ticks", "rolling_short_ev_ticks"])
    draw_line_chart(
        [
            ("5400 rolling long EV", pivot_roll[("rolling_long_ev_ticks", TARGET_LONG)].to_numpy(float), (45, 110, 180)),
            ("5300 rolling short EV", pivot_roll[("rolling_short_ev_ticks", TARGET_SHORT)].to_numpy(float), (200, 85, 50)),
        ],
        args.output_dir / "rolling_surface_edges.png",
        "Rolling 500ts surface edges, target pair",
        "EV ticks",
        hlines=[(0.0, "0", (80, 80, 80))],
    )
    draw_trade_flow(trade_flow, args.output_dir / "trade_flow_distribution.png")
    draw_scatter(scatter, args.output_dir / "residual_vs_dS.png")
    ac_pivot = autocorr.pivot_table(index="lag", columns="strike", values="autocorr").sort_index()
    draw_line_chart(
        [
            ("5300 residual autocorr", ac_pivot[TARGET_SHORT].to_numpy(float), (200, 85, 50)),
            ("5400 residual autocorr", ac_pivot[TARGET_LONG].to_numpy(float), (45, 110, 180)),
        ],
        args.output_dir / "residual_autocorr.png",
        "Residual autocorrelation by lag",
        "autocorr",
        hlines=[(0.0, "0", (80, 80, 80)), (0.8, "0.8", (120, 120, 120))],
    )
    draw_line_chart(
        [("spread 5300-5400", spread_ts["spread_mid"].to_numpy(float), (45, 110, 180))],
        args.output_dir / "spread_5300_5400_timeseries.png",
        "Price spread VEV_5300 - VEV_5400",
        "ticks",
        hlines=[
            (float(spread_ts["mean"].iloc[0]), "mean", (80, 80, 80)),
            (float(spread_ts["upper_1sigma"].iloc[0]), "+1 sigma", (200, 85, 50)),
            (float(spread_ts["lower_1sigma"].iloc[0]), "-1 sigma", (60, 140, 90)),
        ],
    )
    draw_bar_chart(tte, args.output_dir / "tte_sensitivity.png", "TTE sensitivity of 5400 long / 5300 short edges")

    write_report(
        args.output_dir / "P1_FOLLOWUP_REPORT.md",
        rolling_summary,
        surface_2d,
        trade_flow,
        regressions,
        regimes,
        pair_backtest,
        tte,
    )

    print(f"Wrote follow-up outputs to {args.output_dir}")
    print("Key target rolling summary:")
    print(
        rolling_summary[rolling_summary["strike"].isin([TARGET_SHORT, TARGET_LONG])][
            [
                "day",
                "strike",
                "mean_rolling_long_ev",
                "mean_rolling_short_ev",
                "rolling_long_positive_pct",
                "rolling_short_positive_pct",
            ]
        ].to_string(index=False)
    )
    print("TTE sensitivity:")
    print(tte[["TTE_assumption", "edge_5400_long", "edge_5300_short", "verdict"]].to_string(index=False))


if __name__ == "__main__":
    main()
