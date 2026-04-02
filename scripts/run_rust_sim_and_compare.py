from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fv-mode", default="replay", choices=["replay", "simulate"])
    parser.add_argument("--trade-mode", default="replay-times", choices=["replay-times", "simulate"])
    parser.add_argument("--tomato-support", default="0.25", choices=["continuous", "0.5", "0.25"])
    parser.add_argument("--seed", default="20260401")
    parser.add_argument("--output", default="tmp/rust_simulator_output")
    parser.add_argument("--actual", default="data/round0")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    rust_dir = repo_root / "rust_simulator"

    subprocess.run(
        [
            "cargo",
            "run",
            "--release",
            "--",
            "--fv-mode",
            args.fv_mode,
            "--trade-mode",
            args.trade_mode,
            "--tomato-support",
            args.tomato_support,
            "--seed",
            str(args.seed),
            "--output",
            str(repo_root / args.output),
            "--actual-dir",
            str(repo_root / args.actual),
        ],
        cwd=rust_dir,
        check=True,
    )

    subprocess.run(
        [
            "python3",
            str(repo_root / "scripts" / "compare_simulation.py"),
            "--actual",
            str(repo_root / args.actual),
            "--simulated",
            str(repo_root / args.output / "round0"),
        ],
        cwd=repo_root,
        check=True,
    )


if __name__ == "__main__":
    main()
