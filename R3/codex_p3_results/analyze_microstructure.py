#!/usr/bin/env python3
"""Round 3 market microstructure analysis.

Inputs are the six IMC Prosperity Round 3 CSV files. The script creates:
- Markdown report
- PNG charts
- CSV summary tables

It intentionally uses only pandas/numpy/Pillow so it can run on the bundled
Codex Python runtime without extra package installs.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


HORIZONS = (100, 500, 1000)
TIME_BIN = 10_000
DAY_LENGTH = 1_000_000


PRODUCT_ORDER = [
    "HYDROGEL_PACK",
    "VELVETFRUIT_EXTRACT",
    "VEV_4000",
    "VEV_4500",
    "VEV_5000",
    "VEV_5100",
    "VEV_5200",
    "VEV_5300",
    "VEV_5400",
    "VEV_5500",
    "VEV_6000",
    "VEV_6500",
]


@dataclass(frozen=True)
class Paths:
    data_dir: Path
    output_dir: Path

    @property
    def charts_dir(self) -> Path:
        return self.output_dir / "charts"

    @property
    def tables_dir(self) -> Path:
        return self.output_dir / "tables"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default="/Users/danyballand/Downloads/ROUND_3",
        help="Directory containing prices_round_3_day_*.csv and trades_round_3_day_*.csv",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "output"),
        help="Directory where report, charts, and tables will be written",
    )
    return parser.parse_args()


def extract_day(path: Path) -> int:
    match = re.search(r"_day_(-?\d+)", path.stem)
    if not match:
        raise ValueError(f"Could not extract day from {path.name}")
    return int(match.group(1))


def load_data(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_paths = sorted(data_dir.glob("prices_round_3_day_*.csv"), key=extract_day)
    trade_paths = sorted(data_dir.glob("trades_round_3_day_*.csv"), key=extract_day)
    if not price_paths:
        raise FileNotFoundError(f"No price CSVs found in {data_dir}")
    if not trade_paths:
        raise FileNotFoundError(f"No trade CSVs found in {data_dir}")

    prices = pd.concat(
        [pd.read_csv(path, sep=";") for path in price_paths],
        ignore_index=True,
    )
    trades = pd.concat(
        [pd.read_csv(path, sep=";").assign(day=extract_day(path)) for path in trade_paths],
        ignore_index=True,
    )

    numeric_price_cols = [
        col
        for col in prices.columns
        if col.endswith("_price_1")
        or col.endswith("_price_2")
        or col.endswith("_price_3")
        or col.endswith("_volume_1")
        or col.endswith("_volume_2")
        or col.endswith("_volume_3")
        or col in {"day", "timestamp", "mid_price", "profit_and_loss"}
    ]
    for col in numeric_price_cols:
        prices[col] = pd.to_numeric(prices[col], errors="coerce")

    for col in ["day", "timestamp", "price", "quantity"]:
        trades[col] = pd.to_numeric(trades[col], errors="coerce")

    trades["buyer"] = trades.get("buyer", "").fillna("").astype(str).str.strip()
    trades["seller"] = trades.get("seller", "").fillna("").astype(str).str.strip()
    trades["symbol"] = trades["symbol"].astype(str).str.strip()
    trades["abs_quantity"] = trades["quantity"].abs()
    trades = trades.dropna(subset=["day", "timestamp", "price", "quantity", "symbol"]).copy()
    trades["day"] = trades["day"].astype(int)
    trades["timestamp"] = trades["timestamp"].astype(int)

    prices["product"] = prices["product"].astype(str).str.strip()
    prices["day"] = prices["day"].astype(int)
    prices["timestamp"] = prices["timestamp"].astype(int)
    return prices, trades


def ordered_products(products: Iterable[str]) -> list[str]:
    known = [product for product in PRODUCT_ORDER if product in set(products)]
    extras = sorted(set(products) - set(known))
    return known + extras


def prepare_books(prices: pd.DataFrame) -> pd.DataFrame:
    books = prices.copy()
    bid_vol_cols = [f"bid_volume_{i}" for i in range(1, 4)]
    ask_vol_cols = [f"ask_volume_{i}" for i in range(1, 4)]
    for col in bid_vol_cols + ask_vol_cols:
        books[col] = pd.to_numeric(books[col], errors="coerce").fillna(0.0)
    books["total_bid_vol"] = books[bid_vol_cols].sum(axis=1)
    books["total_ask_vol"] = books[ask_vol_cols].sum(axis=1)
    denom = books["total_bid_vol"] + books["total_ask_vol"]
    books["obi"] = np.where(
        denom > 0,
        (books["total_bid_vol"] - books["total_ask_vol"]) / denom,
        np.nan,
    )
    books["spread"] = books["ask_price_1"] - books["bid_price_1"]
    books = books.sort_values(["product", "day", "timestamp"]).reset_index(drop=True)
    return books


def add_future_mids(frame: pd.DataFrame, books: pd.DataFrame, product_col: str) -> pd.DataFrame:
    out = frame.copy()
    for horizon in HORIZONS:
        future = books[["day", "timestamp", "product", "mid_price"]].copy()
        future["timestamp"] = future["timestamp"] - horizon
        future = future.rename(columns={"mid_price": f"mid_t_plus_{horizon}"})
        out = out.merge(
            future,
            left_on=["day", "timestamp", product_col],
            right_on=["day", "timestamp", "product"],
            how="left",
            suffixes=("", f"_future_{horizon}"),
        )
        if "product_future_" + str(horizon) in out.columns:
            out = out.drop(columns=["product_future_" + str(horizon)])
        if "product_y" in out.columns:
            out = out.drop(columns=["product_y"])
        if "product_x" in out.columns:
            out = out.rename(columns={"product_x": "product"})
    return out


def merge_trade_context(trades: pd.DataFrame, books: pd.DataFrame) -> pd.DataFrame:
    top = books[
        [
            "day",
            "timestamp",
            "product",
            "bid_price_1",
            "ask_price_1",
            "bid_volume_1",
            "ask_volume_1",
            "mid_price",
            "spread",
            "obi",
        ]
    ].copy()
    ctx = trades.merge(
        top,
        left_on=["day", "timestamp", "symbol"],
        right_on=["day", "timestamp", "product"],
        how="left",
    )
    ctx["aggressor_side"] = 0
    buy_mask = ctx["price"].ge(ctx["ask_price_1"])
    sell_mask = ctx["price"].le(ctx["bid_price_1"])
    mid_buy_mask = ctx["aggressor_side"].eq(0) & ctx["price"].gt(ctx["mid_price"])
    mid_sell_mask = ctx["aggressor_side"].eq(0) & ctx["price"].lt(ctx["mid_price"])
    ctx.loc[buy_mask, "aggressor_side"] = 1
    ctx.loc[sell_mask & ~buy_mask, "aggressor_side"] = -1
    ctx.loc[mid_buy_mask, "aggressor_side"] = 1
    ctx.loc[mid_sell_mask, "aggressor_side"] = -1
    ctx["aggressor_label"] = np.select(
        [ctx["aggressor_side"].eq(1), ctx["aggressor_side"].eq(-1)],
        ["buyer_initiated", "seller_initiated"],
        default="unknown",
    )
    ctx = add_future_mids(ctx, books, "symbol")
    for horizon in HORIZONS:
        ctx[f"mid_change_{horizon}"] = ctx[f"mid_t_plus_{horizon}"] - ctx["mid_price"]
        ctx[f"signed_markout_{horizon}"] = (
            ctx["aggressor_side"] * ctx[f"mid_change_{horizon}"]
        )
    return ctx


def product_size_stats(trades: pd.DataFrame) -> pd.DataFrame:
    grouped = trades.groupby("symbol")["abs_quantity"]
    stats = grouped.agg(
        trades="count",
        median_size="median",
        mean_size="mean",
        p95_size=lambda s: float(s.quantile(0.95)),
        max_size="max",
    ).reset_index(names="product")
    return stats


def flag_large_trades(ctx: pd.DataFrame) -> pd.DataFrame:
    out = ctx.copy()
    grp = out.groupby("symbol")["abs_quantity"]
    mean_by_product = grp.transform("mean")
    std_by_product = grp.transform("std").replace(0, np.nan)
    p95_by_product = grp.transform(lambda s: s.quantile(0.95))
    out["size_z"] = (out["abs_quantity"] - mean_by_product) / std_by_product
    out["is_large_trade"] = (out["abs_quantity"] >= p95_by_product) | (out["size_z"] > 2)
    return out


def classify_danger(mean_500: float, hit_rate_500: float, n: int) -> str:
    if n < 5 or pd.isna(mean_500):
        return "LOW_SAMPLE"
    if mean_500 >= 2.0 or (mean_500 >= 1.0 and hit_rate_500 >= 0.62):
        return "HIGH"
    if mean_500 >= 0.4 or (mean_500 > 0 and hit_rate_500 >= 0.56):
        return "MEDIUM"
    return "LOW"


def danger_table(ctx: pd.DataFrame, size_stats: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for product, group in ctx.groupby("symbol"):
        large = group[group["is_large_trade"]].copy()
        inferred = large[large["aggressor_side"].ne(0)].copy()
        row = {
            "product": product,
            "trades": int(len(group)),
            "large_trades": int(len(large)),
            "large_trades_with_side": int(len(inferred)),
        }
        for horizon in HORIZONS:
            values = inferred[f"signed_markout_{horizon}"].dropna()
            row[f"mean_signed_markout_{horizon}"] = float(values.mean()) if len(values) else np.nan
            row[f"positive_markout_rate_{horizon}"] = float((values > 0).mean()) if len(values) else np.nan
        row["danger_score"] = (
            max(row.get("mean_signed_markout_500", 0) or 0, 0)
            + 0.5 * max(row.get("mean_signed_markout_1000", 0) or 0, 0)
        )
        row["danger_level"] = classify_danger(
            row["mean_signed_markout_500"],
            row["positive_markout_rate_500"],
            row["large_trades_with_side"],
        )
        rows.append(row)

    danger = pd.DataFrame(rows)
    danger = danger.merge(size_stats, on="product", how="left")
    if "trades_x" in danger.columns:
        danger = danger.rename(columns={"trades_x": "trades"})
    if "trades_y" in danger.columns:
        danger = danger.drop(columns=["trades_y"])
    level_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "LOW_SAMPLE": 0}
    danger["_rank"] = danger["danger_level"].map(level_rank).fillna(0)
    danger = danger.sort_values(
        ["_rank", "danger_score", "large_trades_with_side"],
        ascending=[False, False, False],
    ).drop(columns="_rank")
    return danger


def temporal_patterns(ctx: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trades = ctx.copy()
    trades["time_bin"] = (trades["timestamp"] // TIME_BIN) * TIME_BIN
    volume = (
        trades.groupby(["day", "time_bin", "symbol"], as_index=False)["abs_quantity"]
        .sum()
        .rename(columns={"symbol": "product", "abs_quantity": "volume"})
    )
    pivot = volume.pivot_table(
        index=["day", "time_bin"], columns="product", values="volume", fill_value=0
    )
    corr = pivot.corr(min_periods=10)
    corr_rows = []
    products = list(corr.columns)
    for i, product_a in enumerate(products):
        for product_b in products[i + 1 :]:
            corr_rows.append(
                {
                    "product_a": product_a,
                    "product_b": product_b,
                    "volume_corr": corr.loc[product_a, product_b],
                }
            )
    corr_pairs = pd.DataFrame(corr_rows).sort_values("volume_corr", ascending=False)

    bin_summary = (
        volume.groupby("time_bin", as_index=False)["volume"]
        .sum()
        .rename(columns={"volume": "total_volume"})
    )
    large = trades[trades["is_large_trade"] & trades["aggressor_side"].ne(0)].copy()
    large_bin = (
        large.groupby("time_bin")["signed_markout_500"]
        .mean()
        .rename("large_trade_markout_500")
        .reset_index()
    )
    bin_summary = bin_summary.merge(large_bin, on="time_bin", how="left")
    return volume, corr_pairs, bin_summary


def obi_predictivity(books: pd.DataFrame) -> pd.DataFrame:
    base = books[["day", "timestamp", "product", "mid_price", "obi"]].copy()
    for horizon in (100, 500):
        future = books[["day", "timestamp", "product", "mid_price"]].copy()
        future["timestamp"] = future["timestamp"] - horizon
        future = future.rename(columns={"mid_price": f"mid_t_plus_{horizon}"})
        base = base.merge(future, on=["day", "timestamp", "product"], how="left")
        base[f"delta_{horizon}"] = base[f"mid_t_plus_{horizon}"] - base["mid_price"]

    rows = []
    quintile_rows = []
    for product, group in base.groupby("product"):
        valid = group.dropna(subset=["obi", "delta_100", "delta_500"]).copy()
        if len(valid) < 50:
            continue
        ranks = valid["obi"].rank(method="first")
        valid["obi_quintile"] = pd.qcut(
            ranks,
            q=5,
            labels=["Q1", "Q2", "Q3", "Q4", "Q5"],
        )
        q = (
            valid.groupby("obi_quintile", observed=False)[["delta_100", "delta_500"]]
            .mean()
            .reindex(["Q1", "Q2", "Q3", "Q4", "Q5"])
        )
        q100 = float(q.loc["Q5", "delta_100"] - q.loc["Q1", "delta_100"])
        q500 = float(q.loc["Q5", "delta_500"] - q.loc["Q1", "delta_500"])
        rows.append(
            {
                "product": product,
                "q5_minus_q1_delta_100": q100,
                "q5_minus_q1_delta_500": q500,
                "obi_predictive": bool(q500 > 2.0),
                "mean_q1_delta_500": float(q.loc["Q1", "delta_500"]),
                "mean_q5_delta_500": float(q.loc["Q5", "delta_500"]),
            }
        )
        for quintile, qrow in q.iterrows():
            quintile_rows.append(
                {
                    "product": product,
                    "obi_quintile": str(quintile),
                    "mean_delta_100": float(qrow["delta_100"]),
                    "mean_delta_500": float(qrow["delta_500"]),
                }
            )

    summary = pd.DataFrame(rows).sort_values("q5_minus_q1_delta_500", ascending=False)
    quintiles = pd.DataFrame(quintile_rows)
    return summary, quintiles


def participant_stats(ctx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for role, side in [("buyer", 1), ("seller", -1)]:
        part = ctx[ctx[role].str.len() > 0].copy()
        if part.empty:
            continue
        part["participant"] = part[role]
        part["participant_role"] = role
        if side == 1:
            part["implicit_pnl_500"] = (part["mid_t_plus_500"] - part["price"]) * part["quantity"]
        else:
            part["implicit_pnl_500"] = (part["price"] - part["mid_t_plus_500"]) * part["quantity"]
        rows.append(part)
    if not rows:
        return pd.DataFrame(
            columns=[
                "participant",
                "trades",
                "avg_size",
                "products_traded",
                "primary_product",
                "implicit_pnl_500",
                "avg_implicit_pnl_500",
                "first_timestamp",
                "last_timestamp",
            ]
        )
    participants = pd.concat(rows, ignore_index=True)
    product_sets = participants.groupby("participant")["symbol"].agg(
        lambda s: ", ".join(sorted(s.unique()))
    )
    primary = (
        participants.groupby(["participant", "symbol"])["quantity"]
        .count()
        .reset_index(name="n")
        .sort_values(["participant", "n"], ascending=[True, False])
        .drop_duplicates("participant")
        .set_index("participant")["symbol"]
    )
    stats = participants.groupby("participant").agg(
        trades=("quantity", "count"),
        avg_size=("abs_quantity", "mean"),
        implicit_pnl_500=("implicit_pnl_500", "sum"),
        avg_implicit_pnl_500=("implicit_pnl_500", "mean"),
        first_timestamp=("timestamp", "min"),
        last_timestamp=("timestamp", "max"),
    )
    stats["products_traded"] = product_sets
    stats["primary_product"] = primary
    stats = stats.reset_index().sort_values("implicit_pnl_500", ascending=False)
    return stats


def side_asymmetry(ctx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for product, group in ctx.groupby("symbol"):
        buys = group[group["aggressor_side"].eq(1)]
        sells = group[group["aggressor_side"].eq(-1)]
        unknown = group[group["aggressor_side"].eq(0)]
        buy_trades = len(buys)
        sell_trades = len(sells)
        buy_volume = buys["abs_quantity"].sum()
        sell_volume = sells["abs_quantity"].sum()
        count_ratio = buy_trades / sell_trades if sell_trades else np.nan
        volume_ratio = buy_volume / sell_volume if sell_volume else np.nan
        if pd.isna(volume_ratio):
            tilt = "unknown"
        elif volume_ratio >= 1.5:
            tilt = "buy-heavy"
        elif volume_ratio <= 1 / 1.5:
            tilt = "sell-heavy"
        else:
            tilt = "balanced"
        rows.append(
            {
                "product": product,
                "buy_trades": buy_trades,
                "sell_trades": sell_trades,
                "unknown_side_trades": len(unknown),
                "buy_sell_trade_ratio": count_ratio,
                "buy_volume": float(buy_volume),
                "sell_volume": float(sell_volume),
                "buy_sell_volume_ratio": volume_ratio,
                "flow_tilt": tilt,
            }
        )
    return pd.DataFrame(rows).sort_values("buy_sell_volume_ratio", ascending=False)


def build_wall_records(books: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    records = []
    for side in ["bid", "ask"]:
        for level in range(1, 4):
            part = books[
                [
                    "day",
                    "timestamp",
                    "product",
                    "mid_price",
                    f"{side}_price_{level}",
                    f"{side}_volume_{level}",
                ]
            ].copy()
            part = part.rename(
                columns={
                    f"{side}_price_{level}": "price",
                    f"{side}_volume_{level}": "volume",
                }
            )
            part["book_side"] = side
            part["level"] = level
            records.append(part)
    levels = pd.concat(records, ignore_index=True)
    levels = levels.dropna(subset=["price", "volume"])
    levels = levels[levels["volume"] > 0].copy()
    thresholds = levels.groupby("product")["volume"].quantile(0.90)
    levels["wall_threshold"] = levels["product"].map(thresholds)
    walls = levels[levels["volume"] > levels["wall_threshold"]].copy()
    return walls, thresholds


def wall_dynamics(ctx: pd.DataFrame, books: pd.DataFrame) -> pd.DataFrame:
    walls, thresholds = build_wall_records(books)
    dedup = (
        walls.sort_values("volume", ascending=False)
        .drop_duplicates(["day", "timestamp", "product", "book_side", "price"])
        .sort_values(["product", "day", "book_side", "price", "timestamp"])
        .copy()
    )
    if dedup.empty:
        return pd.DataFrame()
    group_cols = ["product", "day", "book_side", "price"]
    dedup["prev_ts"] = dedup.groupby(group_cols)["timestamp"].shift(1)
    dedup["new_wall_instance"] = (
        dedup["prev_ts"].isna() | dedup["timestamp"].sub(dedup["prev_ts"]).ne(100)
    )
    dedup["wall_instance"] = dedup.groupby(group_cols)["new_wall_instance"].cumsum()
    life = (
        dedup.groupby(group_cols + ["wall_instance"], as_index=False)
        .agg(
            start_ts=("timestamp", "min"),
            end_ts=("timestamp", "max"),
            observations=("timestamp", "count"),
            max_volume=("volume", "max"),
        )
        .copy()
    )
    life["life_ts"] = life["observations"] * 100

    wall_hits = ctx.merge(
        dedup[
            [
                "day",
                "timestamp",
                "product",
                "book_side",
                "price",
                "volume",
                "wall_threshold",
            ]
        ],
        left_on=["day", "timestamp", "symbol", "price"],
        right_on=["day", "timestamp", "product", "price"],
        how="inner",
        suffixes=("", "_wall"),
    )
    if not wall_hits.empty:
        wall_hits["hit_side"] = np.where(wall_hits["book_side"].eq("ask"), 1, -1)
        wall_hits["wall_hit_markout_100"] = (
            wall_hits["hit_side"] * (wall_hits["mid_t_plus_100"] - wall_hits["mid_price"])
        )

    rows = []
    for product in ordered_products(books["product"].unique()):
        product_life = life[life["product"].eq(product)]
        product_hits = wall_hits[wall_hits["symbol"].eq(product)] if not wall_hits.empty else wall_hits
        values = product_hits["wall_hit_markout_100"].dropna() if not wall_hits.empty else pd.Series(dtype=float)
        rows.append(
            {
                "product": product,
                "wall_volume_p90_threshold": float(thresholds.get(product, np.nan)),
                "wall_instances": int(len(product_life)),
                "median_life_ts": float(product_life["life_ts"].median()) if len(product_life) else np.nan,
                "mean_life_ts": float(product_life["life_ts"].mean()) if len(product_life) else np.nan,
                "wall_hit_trades": int(len(product_hits)),
                "mean_hit_signed_markout_100": float(values.mean()) if len(values) else np.nan,
                "hit_in_direction_rate_100": float((values > 0).mean()) if len(values) else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("mean_hit_signed_markout_100", ascending=False)


def median_spreads(books: pd.DataFrame) -> pd.Series:
    return books.groupby("product")["spread"].median()


def product_recommendations(
    danger: pd.DataFrame,
    obi: pd.DataFrame,
    asymmetry: pd.DataFrame,
    spreads: pd.Series,
    hot_bins: list[int],
) -> pd.DataFrame:
    obi_idx = obi.set_index("product") if not obi.empty else pd.DataFrame()
    asym_idx = asymmetry.set_index("product")
    rows = []
    avoid_text = ", ".join(format_ts_bin(ts) for ts in hot_bins[:5]) if hot_bins else "none"
    for _, row in danger.iterrows():
        product = row["product"]
        spread = spreads.get(product, np.nan)
        markout_500 = row.get("mean_signed_markout_500", np.nan)
        danger_level = row.get("danger_level", "LOW")
        if pd.isna(spread):
            edge = np.nan
        elif danger_level == "HIGH":
            edge = max(math.ceil(spread / 2), math.ceil(max(markout_500, 0)))
        elif danger_level == "MEDIUM":
            edge = max(1, math.ceil(spread / 3), math.ceil(max(markout_500, 0) * 0.7))
        else:
            edge = max(1, math.ceil(spread / 4))
        obi_signal = (
            obi_idx.loc[product, "q5_minus_q1_delta_500"]
            if not obi_idx.empty and product in obi_idx.index
            else np.nan
        )
        if pd.notna(obi_signal) and obi_signal > 2:
            skew = f"use OBI skew strongly (+{obi_signal:.2f} ticks Q5-Q1 / 500ts)"
        elif pd.notna(obi_signal) and obi_signal > 0.75:
            skew = f"use light OBI skew (+{obi_signal:.2f} ticks)"
        elif pd.notna(obi_signal) and obi_signal < -0.75:
            skew = f"contrarian OBI; do not chase ({obi_signal:.2f} ticks)"
        else:
            skew = "OBI weak; keep neutral"
        tilt = asym_idx.loc[product, "flow_tilt"] if product in asym_idx.index else "unknown"
        rows.append(
            {
                "product": product,
                "danger_level": danger_level,
                "median_spread": spread,
                "suggested_min_edge_ticks": edge,
                "obi_action": skew,
                "flow_tilt": tilt,
                "avoid_global_hot_bins": avoid_text,
            }
        )
    return pd.DataFrame(rows)


def score_time_bins(bin_summary: pd.DataFrame) -> pd.DataFrame:
    scored = bin_summary.copy()
    scored["positive_large_trade_markout_500"] = (
        scored["large_trade_markout_500"].fillna(0).clip(lower=0)
    )
    scored["volume_rank_pct"] = scored["total_volume"].rank(pct=True)
    scored["adverse_rank_pct"] = scored["positive_large_trade_markout_500"].rank(pct=True)
    scored["temporal_risk_score"] = (
        0.55 * scored["volume_rank_pct"] + 0.45 * scored["adverse_rank_pct"]
    )
    scored["ts_range"] = scored["time_bin"].apply(format_ts_bin)
    return scored


def fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):,.{digits}f}"
    return str(value)


def format_ts_bin(ts: int | float) -> str:
    if pd.isna(ts):
        return ""
    ts = int(ts)
    return f"{ts:,}-{ts + TIME_BIN - 100:,}"


def markdown_table(
    df: pd.DataFrame,
    columns: list[str],
    headers: list[str] | None = None,
    max_rows: int | None = None,
    digits: int = 2,
) -> str:
    if df.empty:
        return "_Aucune ligne._"
    view = df.loc[:, columns].copy()
    if max_rows is not None:
        view = view.head(max_rows)
    headers = headers or columns
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in view.iterrows():
        out.append("| " + " | ".join(fmt(row[col], digits=digits) for col in columns) + " |")
    return "\n".join(out)


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int = 16, fill=(31, 41, 55), bold: bool = False) -> None:
    draw.text(xy, text, fill=fill, font=load_font(size, bold))


def color_ramp(value: float, max_value: float) -> tuple[int, int, int]:
    if max_value <= 0 or pd.isna(value):
        return (248, 250, 252)
    t = max(0.0, min(1.0, value / max_value))
    # Smooth white -> amber -> red ramp.
    if t < 0.5:
        local = t / 0.5
        r = int(255 * (1 - local) + 253 * local)
        g = int(255 * (1 - local) + 186 * local)
        b = int(255 * (1 - local) + 116 * local)
    else:
        local = (t - 0.5) / 0.5
        r = int(253 * (1 - local) + 185 * local)
        g = int(186 * (1 - local) + 28 * local)
        b = int(116 * (1 - local) + 28 * local)
    return (r, g, b)


def chart_size_histograms(trades: pd.DataFrame, output: Path) -> None:
    products = ordered_products(trades["symbol"].unique())
    cell_w, cell_h = 420, 270
    margin = 48
    title_h = 70
    image = Image.new("RGB", (cell_w * 3 + margin * 2, cell_h * 4 + title_h + margin), "white")
    draw = ImageDraw.Draw(image)
    draw_text(draw, (margin, 22), "Trade size histograms by product", 28, bold=True)
    draw_text(draw, (margin, 54), "Bars show count of public trades for each integer |quantity|.", 15, fill=(71, 85, 105))

    for idx, product in enumerate(products):
        row, col = divmod(idx, 3)
        x0 = margin + col * cell_w
        y0 = title_h + row * cell_h
        pad_l, pad_r, pad_t, pad_b = 58, 18, 42, 44
        plot = (x0 + pad_l, y0 + pad_t, x0 + cell_w - pad_r, y0 + cell_h - pad_b)
        counts = trades.loc[trades["symbol"].eq(product), "abs_quantity"].round().astype(int).value_counts().sort_index()
        max_count = int(counts.max()) if len(counts) else 1
        sizes = counts.index.to_list()
        min_size = min(sizes) if sizes else 0
        max_size = max(sizes) if sizes else 1
        draw.rectangle(plot, outline=(203, 213, 225), width=1)
        draw_text(draw, (x0 + 8, y0 + 8), product, 16, bold=True)
        draw_text(draw, (x0 + 8, y0 + 27), f"n={int(counts.sum())}, max={max_size}", 12, fill=(100, 116, 139))
        if max_size == min_size:
            max_size += 1
        for size_value, count in counts.items():
            x_left = plot[0] + int((size_value - min_size) / (max_size - min_size + 1) * (plot[2] - plot[0]))
            x_right = plot[0] + int((size_value + 1 - min_size) / (max_size - min_size + 1) * (plot[2] - plot[0]))
            x_right = max(x_left + 2, x_right - 1)
            bar_h = int((count / max_count) * (plot[3] - plot[1] - 4))
            draw.rectangle((x_left, plot[3] - bar_h, x_right, plot[3] - 1), fill=(37, 99, 235))
        draw_text(draw, (plot[0] - 44, plot[1] - 2), str(max_count), 10, fill=(100, 116, 139))
        draw_text(draw, (plot[0] - 16, plot[3] - 10), "0", 10, fill=(100, 116, 139))
        draw_text(draw, (plot[0], plot[3] + 12), str(min_size), 10, fill=(100, 116, 139))
        draw_text(draw, (plot[2] - 22, plot[3] + 12), str(max_size), 10, fill=(100, 116, 139))
        draw_text(draw, (plot[0] + 96, plot[3] + 24), "|quantity|", 11, fill=(100, 116, 139))
    image.save(output)


def chart_temporal_heatmap(volume: pd.DataFrame, output: Path) -> None:
    heat = volume.groupby(["product", "time_bin"])["volume"].sum().reset_index()
    products = ordered_products(heat["product"].unique())
    bins = list(range(0, DAY_LENGTH, TIME_BIN))
    matrix = heat.pivot_table(index="product", columns="time_bin", values="volume", fill_value=0)
    matrix = matrix.reindex(index=products, columns=bins, fill_value=0)
    cell_w, cell_h = 14, 32
    left, right, top, bottom = 210, 54, 92, 88
    width = left + len(bins) * cell_w + right
    height = top + len(products) * cell_h + bottom
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw_text(draw, (32, 24), "Temporal volume heatmap", 28, bold=True)
    draw_text(draw, (32, 56), "Total public trade volume by product and 10,000 timestamp bin across all days.", 15, fill=(71, 85, 105))
    vals = np.log1p(matrix.values.astype(float))
    max_val = float(np.nanmax(vals)) if vals.size else 1.0
    for r, product in enumerate(products):
        y = top + r * cell_h
        draw_text(draw, (32, y + 8), product, 13, fill=(31, 41, 55))
        for c, bin_ts in enumerate(bins):
            x = left + c * cell_w
            color = color_ramp(float(np.log1p(matrix.loc[product, bin_ts])), max_val)
            draw.rectangle((x, y, x + cell_w - 1, y + cell_h - 2), fill=color)
    for ts in [0, 250_000, 500_000, 750_000, 990_000]:
        c = bins.index((ts // TIME_BIN) * TIME_BIN)
        x = left + c * cell_w
        draw.line((x, top - 6, x, top + len(products) * cell_h), fill=(148, 163, 184), width=1)
        draw_text(draw, (x - 20, top + len(products) * cell_h + 12), f"{ts//1000}k", 11, fill=(71, 85, 105))
    draw_text(draw, (left + len(bins) * cell_w - 180, height - 42), "timestamp within day", 12, fill=(71, 85, 105))
    # Legend
    legend_x = width - 250
    legend_y = 28
    for i in range(100):
        color = color_ramp(i / 99, 1)
        draw.rectangle((legend_x + i, legend_y, legend_x + i, legend_y + 14), fill=color)
    draw_text(draw, (legend_x, legend_y + 20), "low", 11, fill=(71, 85, 105))
    draw_text(draw, (legend_x + 74, legend_y + 20), "high log volume", 11, fill=(71, 85, 105))
    image.save(output)


def chart_obi(obi: pd.DataFrame, output: Path) -> None:
    products = ordered_products(obi["product"].unique())
    data = obi.set_index("product").reindex(products)
    width, height = 1550, 760
    left, right, top, bottom = 130, 60, 86, 126
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw_text(draw, (42, 24), "OBI predictivity by product", 28, bold=True)
    draw_text(draw, (42, 56), "Bars show Q5 minus Q1 future mid-price change. Positive means high OBI predicts upward moves.", 15, fill=(71, 85, 105))
    vals_100 = data["q5_minus_q1_delta_100"].fillna(0).values
    vals_500 = data["q5_minus_q1_delta_500"].fillna(0).values
    max_abs = max(1.0, float(np.nanmax(np.abs(np.concatenate([vals_100, vals_500])))))
    plot_h = height - top - bottom
    zero_y = top + plot_h // 2
    scale = (plot_h / 2 - 20) / max_abs
    draw.line((left, zero_y, width - right, zero_y), fill=(100, 116, 139), width=1)
    for tick in [-max_abs, -max_abs / 2, 0, max_abs / 2, max_abs]:
        y = zero_y - int(tick * scale)
        draw.line((left - 6, y, width - right, y), fill=(226, 232, 240), width=1)
        draw_text(draw, (42, y - 8), f"{tick:.1f}", 11, fill=(100, 116, 139))
    group_w = (width - left - right) / len(products)
    bar_w = max(8, int(group_w * 0.25))
    for i, product in enumerate(products):
        cx = left + int((i + 0.5) * group_w)
        for offset, value, color in [
            (-bar_w // 2 - 2, vals_100[i], (14, 165, 233)),
            (bar_w // 2 + 2, vals_500[i], (22, 163, 74) if vals_500[i] >= 0 else (220, 38, 38)),
        ]:
            x0 = cx + offset - bar_w // 2
            x1 = x0 + bar_w
            y = zero_y - int(value * scale)
            draw.rectangle((x0, min(y, zero_y), x1, max(y, zero_y)), fill=color)
        label = product.replace("VELVETFRUIT_", "VF_").replace("HYDROGEL_", "HYD_")
        draw_text(draw, (cx - 45, height - bottom + 20), label, 10, fill=(71, 85, 105))
    draw.rectangle((width - 310, 28, width - 292, 46), fill=(14, 165, 233))
    draw_text(draw, (width - 286, 29), "100 ts", 12, fill=(71, 85, 105))
    draw.rectangle((width - 220, 28, width - 202, 46), fill=(22, 163, 74))
    draw_text(draw, (width - 196, 29), "500 ts", 12, fill=(71, 85, 105))
    image.save(output)


def chart_danger(danger: pd.DataFrame, output: Path) -> None:
    data = danger.sort_values("danger_score", ascending=True).copy()
    width, height = 1400, 760
    left, right, top, bottom = 260, 250, 82, 70
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw_text(draw, (42, 24), "Danger score: large-trade signed markout", 28, bold=True)
    draw_text(draw, (42, 56), "Score = positive 500ts markout + 0.5 * positive 1000ts markout on P95+/Z>2 trades.", 15, fill=(71, 85, 105))
    max_val = max(1.0, float(data["danger_score"].fillna(0).max()))
    row_h = (height - top - bottom) / max(len(data), 1)
    for i, (_, row) in enumerate(data.iterrows()):
        y = top + int(i * row_h)
        product = row["product"]
        level = row["danger_level"]
        value = float(row["danger_score"] or 0)
        color = {
            "HIGH": (220, 38, 38),
            "MEDIUM": (245, 158, 11),
            "LOW": (22, 163, 74),
            "LOW_SAMPLE": (148, 163, 184),
        }.get(level, (100, 116, 139))
        draw_text(draw, (42, y + int(row_h / 2) - 8), product, 13, fill=(31, 41, 55))
        x0 = left
        x1 = left + int(value / max_val * (width - left - right))
        draw.rectangle((x0, y + 7, x1, y + int(row_h) - 7), fill=color)
        draw_text(draw, (x1 + 8, y + int(row_h / 2) - 8), f"{value:.2f} ({level})", 12, fill=(71, 85, 105))
    image.save(output)


def write_report(
    paths: Paths,
    prices: pd.DataFrame,
    ctx: pd.DataFrame,
    size_stats: pd.DataFrame,
    danger: pd.DataFrame,
    volume: pd.DataFrame,
    corr_pairs: pd.DataFrame,
    bin_summary: pd.DataFrame,
    obi: pd.DataFrame,
    participants: pd.DataFrame,
    asymmetry: pd.DataFrame,
    walls: pd.DataFrame,
    recs: pd.DataFrame,
) -> None:
    report_path = paths.output_dir / "R3_MICROSTRUCTURE_REPORT.md"
    blank_buyer_rate = float((ctx["buyer"].str.len() == 0).mean())
    blank_seller_rate = float((ctx["seller"].str.len() == 0).mean())

    scored_bins = score_time_bins(bin_summary)
    hot_bins = scored_bins.sort_values("total_volume", ascending=False).head(8)
    calm_bins = scored_bins.sort_values("total_volume", ascending=True).head(8)
    safe_bins = scored_bins.sort_values("temporal_risk_score", ascending=True).head(8)
    avoid_bins = scored_bins.sort_values("temporal_risk_score", ascending=False).head(8)

    dangerous = danger[danger["danger_level"].isin(["HIGH", "MEDIUM"])].head(6)
    if dangerous.empty:
        dangerous_text = "Aucun produit ne ressort HIGH/MEDIUM sur les gros trades avec side inferee."
    else:
        dangerous_text = ", ".join(
            f"{r.product} ({r.danger_level}, m500={fmt(r.mean_signed_markout_500)})"
            for r in dangerous.itertuples()
        )

    if participants.empty:
        trader_text = (
            "Aucun ID exploitable: 100% des champs buyer et seller sont vides dans ces fichiers. "
            "Le side-channel par identite n'est donc pas observable ici."
        )
    else:
        trader_text = ", ".join(
            f"{r.participant} (PnL500={fmt(r.implicit_pnl_500)})"
            for r in participants.head(3).itertuples()
        )

    safest_text = ", ".join(safe_bins["ts_range"].head(5))
    avoid_text = ", ".join(format_ts_bin(ts) for ts in avoid_bins["time_bin"].head(5))

    lines = [
        "# R3 Microstructure & Informed Flow Report",
        "",
        "## Executive summary",
        "",
        f"- **Produits dangereux:** {dangerous_text}",
        f"- **Side-channel trader ID:** {trader_text}",
        f"- **Fenetre MM plus calme:** {safest_text}. **A eviter / elargir:** {avoid_text}.",
        "",
        "## Methodologie",
        "",
        "- Side des trades publics infere par comparaison du prix trade avec bid/ask L1, puis mid si besoin.",
        "- Markout signe = side_agresseur * (mid futur - mid courant). Positif veut dire que le trade public etait adverse pour un market maker qui quote contre lui.",
        "- Gros trade = taille >= P95 du produit ou Z-score taille > 2.",
        "- OBI = (volume bid total L1-L3 - volume ask total L1-L3) / total volume L1-L3.",
        "- Walls = niveaux de carnet avec volume strictement superieur au P90 du produit.",
        "",
        f"Dataset: {len(prices):,} lignes de carnet, {len(ctx):,} trades publics, {ctx['symbol'].nunique()} produits.",
        f"Champs ID vides: buyer {blank_buyer_rate:.1%}, seller {blank_seller_rate:.1%}.",
        "",
        "## Charts",
        "",
        f"![Trade size histograms](charts/trade_size_histograms.png)",
        "",
        f"![Temporal volume heatmap](charts/temporal_volume_heatmap.png)",
        "",
        f"![OBI predictivity](charts/obi_predictivity.png)",
        "",
        f"![Danger score](charts/danger_score.png)",
        "",
        "## Danger level par produit",
        "",
        markdown_table(
            danger,
            [
                "product",
                "danger_level",
                "trades",
                "large_trades_with_side",
                "p95_size",
                "mean_signed_markout_100",
                "mean_signed_markout_500",
                "mean_signed_markout_1000",
                "positive_markout_rate_500",
            ],
            [
                "Product",
                "Danger",
                "Trades",
                "Large sided",
                "P95 size",
                "M100",
                "M500",
                "M1000",
                "Hit rate 500",
            ],
        ),
        "",
        "## Distribution des tailles",
        "",
        markdown_table(
            size_stats.sort_values("p95_size", ascending=False),
            ["product", "trades", "median_size", "mean_size", "p95_size", "max_size"],
            ["Product", "Trades", "Median", "Mean", "P95", "Max"],
        ),
        "",
        "## Patterns temporels",
        "",
        "### Bins preferables pour MM",
        "",
        markdown_table(
            safe_bins,
            ["ts_range", "total_volume", "large_trade_markout_500", "temporal_risk_score"],
            ["TS bin", "Total volume", "Large trade M500", "Risk score"],
        ),
        "",
        "### Bins les plus chauds",
        "",
        markdown_table(
            hot_bins,
            ["ts_range", "total_volume", "large_trade_markout_500"],
            ["TS bin", "Total volume", "Large trade M500"],
        ),
        "",
        "### Bins les plus calmes",
        "",
        markdown_table(
            calm_bins,
            ["ts_range", "total_volume", "large_trade_markout_500"],
            ["TS bin", "Total volume", "Large trade M500"],
        ),
        "",
        "### Correlations de volume inter-produits",
        "",
        markdown_table(
            corr_pairs.dropna().head(12),
            ["product_a", "product_b", "volume_corr"],
            ["Product A", "Product B", "Corr"],
        ),
        "",
        "## OBI predictif",
        "",
        markdown_table(
            obi,
            [
                "product",
                "q5_minus_q1_delta_100",
                "q5_minus_q1_delta_500",
                "obi_predictive",
                "mean_q1_delta_500",
                "mean_q5_delta_500",
            ],
            ["Product", "Q5-Q1 100", "Q5-Q1 500", "Predictive >2", "Q1 d500", "Q5 d500"],
        ),
        "",
        "## Identification traders",
        "",
    ]
    if participants.empty:
        lines += [
            "Aucun top trader ID ne peut etre calcule: tous les champs `buyer` et `seller` sont vides.",
            "Le script exporte quand meme `tables/trader_stats.csv` pour garder le workflow reproductible si une version des donnees contient les IDs.",
        ]
    else:
        lines += [
            markdown_table(
                participants,
                [
                    "participant",
                    "trades",
                    "avg_size",
                    "products_traded",
                    "primary_product",
                    "implicit_pnl_500",
                    "avg_implicit_pnl_500",
                ],
                ["ID", "Trades", "Avg size", "Products", "Primary", "PnL500", "Avg PnL500"],
                max_rows=10,
            )
        ]
    lines += [
        "",
        "## Wall dynamics",
        "",
        markdown_table(
            walls,
            [
                "product",
                "wall_volume_p90_threshold",
                "wall_instances",
                "median_life_ts",
                "wall_hit_trades",
                "mean_hit_signed_markout_100",
                "hit_in_direction_rate_100",
            ],
            ["Product", "P90 vol", "Wall instances", "Median life ts", "Hits", "Hit M100", "In-dir rate"],
        ),
        "",
        "## Asymetrie buy/sell inferee",
        "",
        markdown_table(
            asymmetry,
            [
                "product",
                "buy_trades",
                "sell_trades",
                "unknown_side_trades",
                "buy_sell_trade_ratio",
                "buy_sell_volume_ratio",
                "flow_tilt",
            ],
            ["Product", "Buy trades", "Sell trades", "Unknown", "Count ratio", "Volume ratio", "Tilt"],
        ),
        "",
        "## Recommandations MM concretes",
        "",
        markdown_table(
            recs,
            [
                "product",
                "danger_level",
                "median_spread",
                "suggested_min_edge_ticks",
                "obi_action",
                "flow_tilt",
                "avoid_global_hot_bins",
            ],
            ["Product", "Danger", "Median spread", "Min edge", "OBI action", "Flow tilt", "Avoid bins"],
        ),
        "",
        "## Fichiers generes",
        "",
        "- `tables/product_size_stats.csv`",
        "- `tables/danger_table.csv`",
        "- `tables/temporal_volume_by_product_bin.csv`",
        "- `tables/temporal_bin_summary.csv`",
        "- `tables/volume_correlations.csv`",
        "- `tables/obi_predictivity.csv`",
        "- `tables/obi_quintiles.csv`",
        "- `tables/trader_stats.csv`",
        "- `tables/wall_dynamics.csv`",
        "- `tables/asymmetry.csv`",
        "- `tables/mm_recommendations.csv`",
        "",
        "## Limites",
        "",
        "- Les buyer/seller IDs etant vides, toute conclusion sur un trader nomme est impossible avec ces fichiers.",
        "- Le side public est infere, pas donne explicitement. Les trades au mid restent inconnus.",
        "- Les walls sont observes sur snapshots 100 ts; une wall peut apparaitre/disparaitre entre deux snapshots.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_tables(
    paths: Paths,
    size_stats: pd.DataFrame,
    danger: pd.DataFrame,
    volume: pd.DataFrame,
    corr_pairs: pd.DataFrame,
    bin_summary: pd.DataFrame,
    obi: pd.DataFrame,
    obi_quintiles: pd.DataFrame,
    participants: pd.DataFrame,
    asymmetry: pd.DataFrame,
    walls: pd.DataFrame,
    recs: pd.DataFrame,
) -> None:
    tables = {
        "product_size_stats.csv": size_stats,
        "danger_table.csv": danger,
        "temporal_volume_by_product_bin.csv": volume,
        "temporal_bin_summary.csv": bin_summary,
        "volume_correlations.csv": corr_pairs,
        "obi_predictivity.csv": obi,
        "obi_quintiles.csv": obi_quintiles,
        "trader_stats.csv": participants,
        "asymmetry.csv": asymmetry,
        "wall_dynamics.csv": walls,
        "mm_recommendations.csv": recs,
    }
    for name, table in tables.items():
        table.to_csv(paths.tables_dir / name, index=False)


def main() -> None:
    args = parse_args()
    paths = Paths(Path(args.data_dir).expanduser(), Path(args.output_dir).expanduser())
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.charts_dir.mkdir(parents=True, exist_ok=True)
    paths.tables_dir.mkdir(parents=True, exist_ok=True)

    prices, trades = load_data(paths.data_dir)
    books = prepare_books(prices)
    ctx = merge_trade_context(trades, books)
    ctx = flag_large_trades(ctx)

    size_stats = product_size_stats(trades)
    danger = danger_table(ctx, size_stats)
    volume, corr_pairs, bin_summary = temporal_patterns(ctx)
    obi, obi_quintiles = obi_predictivity(books)
    participants = participant_stats(ctx)
    asymmetry = side_asymmetry(ctx)
    walls = wall_dynamics(ctx, books)
    spreads = median_spreads(books)
    temporal_avoid_bins = (
        score_time_bins(bin_summary)
        .sort_values("temporal_risk_score", ascending=False)["time_bin"]
        .head(5)
        .tolist()
    )
    recs = product_recommendations(danger, obi, asymmetry, spreads, temporal_avoid_bins)

    save_tables(
        paths,
        size_stats,
        danger,
        volume,
        corr_pairs,
        bin_summary,
        obi,
        obi_quintiles,
        participants,
        asymmetry,
        walls,
        recs,
    )
    chart_size_histograms(ctx, paths.charts_dir / "trade_size_histograms.png")
    chart_temporal_heatmap(volume, paths.charts_dir / "temporal_volume_heatmap.png")
    chart_obi(obi, paths.charts_dir / "obi_predictivity.png")
    chart_danger(danger, paths.charts_dir / "danger_score.png")
    write_report(
        paths,
        prices,
        ctx,
        size_stats,
        danger,
        volume,
        corr_pairs,
        bin_summary,
        obi,
        participants,
        asymmetry,
        walls,
        recs,
    )

    print(f"Wrote report: {paths.output_dir / 'R3_MICROSTRUCTURE_REPORT.md'}")
    print(f"Wrote charts: {paths.charts_dir}")
    print(f"Wrote tables: {paths.tables_dir}")


if __name__ == "__main__":
    main()
