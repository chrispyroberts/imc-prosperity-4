from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd


def load_round0_dataset(root: str | Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(root)
    if (root / "round0").exists():
        root = root / "round0"

    price_frames = []
    trade_frames = []
    for day in (-2, -1):
        price = pd.read_csv(root / f"prices_round_0_day_{day}.csv", sep=";")
        trade = pd.read_csv(root / f"trades_round_0_day_{day}.csv", sep=";")
        price["day"] = day
        trade["day"] = day
        price_frames.append(price)
        trade_frames.append(trade)

    prices = pd.concat(price_frames, ignore_index=True)
    trades = pd.concat(trade_frames, ignore_index=True)
    return prices, trades


def enrich_prices(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    bid_cols = [f"bid_price_{i}" for i in (1, 2, 3)]
    ask_cols = [f"ask_price_{i}" for i in (1, 2, 3)]
    df["fair"] = (df[bid_cols].min(axis=1) + df[ask_cols].max(axis=1)) / 2
    df["extra_state"] = "none"
    df.loc[df["bid_price_3"].notna() & df["ask_price_3"].isna(), "extra_state"] = "bid_only"
    df.loc[df["ask_price_3"].notna() & df["bid_price_3"].isna(), "extra_state"] = "ask_only"
    df["latent_fair"] = df["fair"]

    tomatoes = df["product"] == "TOMATOES"
    if tomatoes.any():
        outer_bid = np.select(
            [
                df["extra_state"] == "none",
                df["extra_state"] == "bid_only",
                df["extra_state"] == "ask_only",
            ],
            [df["bid_price_2"], df["bid_price_3"], df["bid_price_2"]],
            default=np.nan,
        )
        outer_ask = np.select(
            [
                df["extra_state"] == "none",
                df["extra_state"] == "bid_only",
                df["extra_state"] == "ask_only",
            ],
            [df["ask_price_2"], df["ask_price_2"], df["ask_price_3"]],
            default=np.nan,
        )
        inner_bid = np.select(
            [
                df["extra_state"] == "none",
                df["extra_state"] == "bid_only",
                df["extra_state"] == "ask_only",
            ],
            [df["bid_price_1"], df["bid_price_2"], df["bid_price_1"]],
            default=np.nan,
        )
        inner_ask = np.select(
            [
                df["extra_state"] == "none",
                df["extra_state"] == "bid_only",
                df["extra_state"] == "ask_only",
            ],
            [df["ask_price_1"], df["ask_price_1"], df["ask_price_2"]],
            default=np.nan,
        )

        low = np.maximum.reduce(
            [
                outer_bid + 7.5,
                outer_ask - 8.5,
                inner_bid + 6.0,
                inner_ask - 7.0,
            ]
        )
        high = np.minimum.reduce(
            [
                outer_bid + 8.5,
                outer_ask - 7.5,
                inner_bid + 7.0,
                inner_ask - 6.0,
            ]
        )
        latent = (low + high) / 2.0
        valid = tomatoes & np.isfinite(latent) & (low <= high)
        df.loc[valid, "latent_fair"] = latent[valid]
    return df


def summarize_fair(prices: pd.DataFrame) -> pd.DataFrame:
    df = enrich_prices(prices)
    rows = []
    for (product, day), sub in df.groupby(["product", "day"]):
        sub = sub.sort_values("timestamp").copy()
        rets = sub["fair"].diff().dropna()
        latent_rets = sub["latent_fair"].diff().dropna()
        ret_abs = rets.abs()
        rows.append(
            {
                "product": product,
                "day": day,
                "start": sub["fair"].iloc[0],
                "end": sub["fair"].iloc[-1],
                "latent_start": sub["latent_fair"].iloc[0],
                "latent_end": sub["latent_fair"].iloc[-1],
                "range_min": sub["fair"].min(),
                "range_max": sub["fair"].max(),
                "std": sub["fair"].std(),
                "ac1": rets.autocorr(lag=1) if len(rets) > 1 else np.nan,
                "latent_std": sub["latent_fair"].std(),
                "latent_ac1": latent_rets.autocorr(lag=1) if len(latent_rets) > 1 else np.nan,
                "ret0": (ret_abs == 0).mean(),
                "ret0_5": (ret_abs == 0.5).mean(),
                "ret1": (ret_abs == 1.0).mean(),
                "ret1_5": (ret_abs == 1.5).mean(),
                "ret2": (ret_abs == 2.0).mean(),
            }
        )
    return pd.DataFrame(rows).sort_values(["product", "day"]).reset_index(drop=True)


def summarize_books(prices: pd.DataFrame) -> pd.DataFrame:
    df = enrich_prices(prices)
    rows = []
    for product, sub in df.groupby("product"):
        bid3 = sub["bid_price_3"].notna()
        ask3 = sub["ask_price_3"].notna()
        cases = {
            "none": ~bid3 & ~ask3,
            "bid_only": bid3 & ~ask3,
            "ask_only": ~bid3 & ask3,
        }

        inner_vol = pd.concat(
            [
                sub.loc[cases["none"], "bid_volume_1"],
                sub.loc[cases["bid_only"], "bid_volume_2"],
                sub.loc[cases["ask_only"], "bid_volume_1"],
            ],
            ignore_index=True,
        )
        outer_vol = pd.concat(
            [
                sub.loc[cases["none"], "bid_volume_2"],
                sub.loc[cases["bid_only"], "bid_volume_3"],
                sub.loc[cases["ask_only"], "bid_volume_2"],
            ],
            ignore_index=True,
        )
        row = {
            "product": product,
            "none_rate": cases["none"].mean(),
            "bid_only_rate": cases["bid_only"].mean(),
            "ask_only_rate": cases["ask_only"].mean(),
            "inner_size_mean": inner_vol.mean(),
            "outer_size_mean": outer_vol.mean(),
            "inner_size_min": inner_vol.min(),
            "inner_size_max": inner_vol.max(),
            "outer_size_min": outer_vol.min(),
            "outer_size_max": outer_vol.max(),
        }

        if product == "TOMATOES":
            base = sub[cases["none"]].copy()
            int_base = base[(base["fair"] % 1).abs() < 1e-9].copy()
            half_base = base[(base["fair"] % 1 - 0.5).abs() < 1e-9].copy()
            combo_all = pd.Series(
                list(zip(base["bid_price_1"] - base["fair"], base["ask_price_1"] - base["fair"])),
                dtype=object,
            )
            combo_int = pd.Series(
                list(zip(int_base["bid_price_1"] - int_base["fair"], int_base["ask_price_1"] - int_base["fair"])),
                dtype=object,
            )
            combo_half = pd.Series(
                list(zip(half_base["bid_price_1"] - half_base["fair"], half_base["ask_price_1"] - half_base["fair"])),
                dtype=object,
            )
            combo_all_share = combo_all.value_counts(normalize=True).to_dict()
            combo_int_share = combo_int.value_counts(normalize=True).to_dict()
            combo_half_share = combo_half.value_counts(normalize=True).to_dict()
            outer_spread = (half_base["ask_price_2"] - half_base["bid_price_2"]).value_counts(normalize=True).to_dict()
            row.update(
                {
                    "outer_half_mid_rate": len(half_base) / len(base) if len(base) else np.nan,
                    "inner_all_-7_7": combo_all_share.get((-7.0, 7.0), 0.0),
                    "inner_all_-7_6": combo_all_share.get((-7.0, 6.0), 0.0),
                    "inner_all_-6_7": combo_all_share.get((-6.0, 7.0), 0.0),
                    "inner_all_-6_5_6_5": combo_all_share.get((-6.5, 6.5), 0.0),
                    "inner_int_-7_7": combo_int_share.get((-7.0, 7.0), 0.0),
                    "inner_int_-7_6": combo_int_share.get((-7.0, 6.0), 0.0),
                    "inner_int_-6_7": combo_int_share.get((-6.0, 7.0), 0.0),
                    "inner_half_-6_5_6_5": combo_half_share.get((-6.5, 6.5), 0.0),
                    "outer_half_spread15": outer_spread.get(15, 0.0),
                    "outer_half_spread17": outer_spread.get(17, 0.0),
                }
            )
        else:
            row.update(
                {
                    "outer_half_mid_rate": np.nan,
                    "inner_all_-7_7": np.nan,
                    "inner_all_-7_6": np.nan,
                    "inner_all_-6_7": np.nan,
                    "inner_all_-6_5_6_5": np.nan,
                    "inner_int_-7_7": np.nan,
                    "inner_int_-7_6": np.nan,
                    "inner_int_-6_7": np.nan,
                    "inner_half_-6_5_6_5": np.nan,
                    "outer_half_spread15": np.nan,
                    "outer_half_spread17": np.nan,
                }
            )

        rows.append(row)
    return pd.DataFrame(rows).sort_values("product").reset_index(drop=True)


def summarize_bot3(prices: pd.DataFrame) -> pd.DataFrame:
    df = enrich_prices(prices)
    rows = []
    for product, sub in df.groupby("product"):
        bid_only = sub[sub["extra_state"] == "bid_only"].copy()
        ask_only = sub[sub["extra_state"] == "ask_only"].copy()
        bid_fair = bid_only["latent_fair"]
        ask_fair = ask_only["latent_fair"]

        if product == "EMERALDS":
            bid_regime = pd.Series(np.where(bid_only["bid_price_1"] >= bid_fair, "aggressive", "passive"))
            ask_regime = pd.Series(np.where(ask_only["ask_price_1"] <= ask_fair, "aggressive", "passive"))
            bid_size = bid_only["bid_volume_1"]
            ask_size = ask_only["ask_volume_1"]
        else:
            bid_offset = bid_only["bid_price_1"] - bid_fair
            ask_offset = ask_only["ask_price_1"] - ask_fair
            bid_regime = pd.Series(np.where(bid_offset >= 0, "aggressive", "passive"))
            ask_regime = pd.Series(np.where(ask_offset <= -1, "aggressive", "passive"))
            bid_size = bid_only["bid_volume_1"]
            ask_size = ask_only["ask_volume_1"]

        rows.append(
            {
                "product": product,
                "bid_aggressive_rate": (bid_regime == "aggressive").mean() if len(bid_regime) else np.nan,
                "ask_aggressive_rate": (ask_regime == "aggressive").mean() if len(ask_regime) else np.nan,
                "bid_size_mean": bid_size.mean() if len(bid_size) else np.nan,
                "ask_size_mean": ask_size.mean() if len(ask_size) else np.nan,
                "bid_events": len(bid_only),
                "ask_events": len(ask_only),
            }
        )
    return pd.DataFrame(rows).sort_values("product").reset_index(drop=True)


def summarize_trades(prices: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    enriched = enrich_prices(prices)
    rows = []
    for (symbol, day), sub in trades.groupby(["symbol", "day"]):
        sub = sub.sort_values("timestamp").copy()
        gap = sub["timestamp"].diff().dropna()
        qty_counts = sub["quantity"].value_counts(normalize=True).to_dict()
        rows.append(
            {
                "product": symbol,
                "day": day,
                "trade_count": len(sub),
                "mean_gap": gap.mean() if len(gap) else np.nan,
                "qty2": qty_counts.get(2, 0.0),
                "qty3": qty_counts.get(3, 0.0),
                "qty4": qty_counts.get(4, 0.0),
                "qty5": qty_counts.get(5, 0.0),
                "qty6": qty_counts.get(6, 0.0),
                "qty7": qty_counts.get(7, 0.0),
                "qty8": qty_counts.get(8, 0.0),
            }
        )
    return pd.DataFrame(rows).sort_values(["product", "day"]).reset_index(drop=True)


def compare_frames(actual: pd.DataFrame, simulated: pd.DataFrame, keys: Iterable[str]) -> pd.DataFrame:
    keys = list(keys)
    merged = actual.merge(simulated, on=keys, how="outer", suffixes=("_actual", "_sim"))
    for col in list(merged.columns):
        if col.endswith("_actual"):
            base = col[:-7]
            sim_col = f"{base}_sim"
            if sim_col in merged.columns and np.issubdtype(merged[col].dtype, np.number):
                merged[f"{base}_diff"] = merged[sim_col] - merged[col]
    return merged.sort_values(keys).reset_index(drop=True)
