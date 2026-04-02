from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from sim_analysis import (
    compare_frames,
    load_round0_dataset,
    summarize_books,
    summarize_bot3,
    summarize_fair,
    summarize_trades,
)

def print_section(title: str, frame: pd.DataFrame) -> None:
    print(f"\n=== {title} ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(frame.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual", default="data/round0")
    parser.add_argument("--simulated", default="tmp/rust_simulator_output/round0")
    args = parser.parse_args()

    actual_prices, actual_trades = load_round0_dataset(Path(args.actual))
    sim_prices, sim_trades = load_round0_dataset(Path(args.simulated))

    fair_cmp = compare_frames(summarize_fair(actual_prices), summarize_fair(sim_prices), ["product", "day"])
    book_cmp = compare_frames(summarize_books(actual_prices), summarize_books(sim_prices), ["product"])
    bot3_cmp = compare_frames(summarize_bot3(actual_prices), summarize_bot3(sim_prices), ["product"])
    trade_cmp = compare_frames(
        summarize_trades(actual_prices, actual_trades),
        summarize_trades(sim_prices, sim_trades),
        ["product", "day"],
    )

    print_section("Fair Summary", fair_cmp.round(4))
    print_section("Book Summary", book_cmp.round(4))
    print_section("Bot 3 Summary", bot3_cmp.round(4))
    print_section("Trade Summary", trade_cmp.round(4))


if __name__ == "__main__":
    main()
