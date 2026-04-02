#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("strategy")
    parser.add_argument("--sessions", type=int, default=100)
    parser.add_argument("--output", default="tmp/strategy_backtests")
    parser.add_argument("--fv-mode", default="simulate", choices=["simulate", "replay"])
    parser.add_argument("--trade-mode", default="simulate", choices=["simulate", "replay-times"])
    parser.add_argument("--tomato-support", default="quarter", choices=["continuous", "half", "quarter", "0.5", "0.25"])
    parser.add_argument("--seed", type=int, default=20260401)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    rust_dir = root / "rust_simulator"
    output_dir = root / args.output
    strategy_path = Path(args.strategy).resolve() if not Path(args.strategy).is_absolute() else Path(args.strategy)

    cmd = [
        "cargo",
        "run",
        "--release",
        "--",
        "--strategy",
        str(strategy_path),
        "--sessions",
        str(args.sessions),
        "--output",
        str(output_dir),
        "--fv-mode",
        args.fv_mode,
        "--trade-mode",
        args.trade_mode,
        "--tomato-support",
        args.tomato_support,
        "--seed",
        str(args.seed),
    ]
    subprocess.run(cmd, cwd=rust_dir, check=True)

    summary = pd.read_csv(output_dir / "session_summary.csv")
    print(f"sessions={len(summary)}")
    print(
        summary["total_pnl"]
        .describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95])
        .round(4)
        .to_string()
    )


if __name__ == "__main__":
    main()
