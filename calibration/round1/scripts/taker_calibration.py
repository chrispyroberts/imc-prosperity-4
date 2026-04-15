"""Fits taker arrival + side + volume distributions from Round 1 trade CSVs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


TRADES_DIR = Path("/Users/liam/local/brain/workspaces/imc-prosperity/imc-prosperity-4-main/ROUND1/ROUND_1")
TRADE_FILES = [
    TRADES_DIR / "trades_round_1_day_-2.csv",
    TRADES_DIR / "trades_round_1_day_-1.csv",
    TRADES_DIR / "trades_round_1_day_0.csv",
]
TICKS_PER_DAY = 10_000


def fit_taker(product: str, trade_files: list[Path]) -> dict:
    frames = []
    for f in trade_files:
        if not f.exists():
            continue
        df = pd.read_csv(f, sep=";")
        df = df[df["symbol"] == product].copy()
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no trade files loaded from {trade_files}")
    df = pd.concat(frames, ignore_index=True)

    n_days = len(frames)
    total_ticks = n_days * TICKS_PER_DAY
    n_trades = len(df)
    trade_active_prob = n_trades / total_ticks

    ticks_with_any = df["timestamp"].nunique()
    ticks_with_two_plus = int((df.groupby("timestamp").size() >= 2).sum())
    second_trade_prob = ticks_with_two_plus / ticks_with_any if ticks_with_any else 0.0

    # buyer/seller fields are empty in round1 CSVs; default buy_prob=0.5 (Jeffreys prior)
    buy_prob = 0.5
    buy_prob_alpha = 1.0
    buy_prob_beta = 1.0

    trade_active_beta = [int(n_trades + 1), int(total_ticks - n_trades + 1)]
    second_trade_beta = [int(ticks_with_two_plus + 1), int(ticks_with_any - ticks_with_two_plus + 1)]

    return {
        "product": product,
        "n_days": n_days,
        "n_trades": n_trades,
        "total_ticks": total_ticks,
        "ticks_with_any_trade": int(ticks_with_any),
        "ticks_with_two_plus_trades": ticks_with_two_plus,
        "trade_active_prob": trade_active_prob,
        "second_trade_prob": float(second_trade_prob),
        "buy_prob": buy_prob,
        "buy_prob_beta": [buy_prob_alpha, buy_prob_beta],
        "trade_active_beta": trade_active_beta,
        "second_trade_beta": second_trade_beta,
        "buy_prob_note": (
            "buyer/seller fields empty in round1 trades; "
            "buy_prob defaulted to 0.5 with Jeffreys prior Beta(1,1)"
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--out", type=Path, help="optional JSON output path")
    args = ap.parse_args()
    result = fit_taker(args.product, TRADE_FILES)
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
