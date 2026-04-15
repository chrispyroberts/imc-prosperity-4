"""Fit and select FV process model for OSMIUM.

Trains on day 0 server FV (first 67%) with held-out log-likelihood on last 33%.
Cross-validates parameter estimates against historical mid-price days -2/-1.
Bootstrap posterior for rust TOML emission.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from calibration.round1.lib.fv_process import select_fv_model, bootstrap_posterior


PRODUCT = "ASH_COATED_OSMIUM"
FV_PATH = Path("calibration/round1/data/fv_and_book_ash_coated_osmium.json")
HISTORICAL_CSV_DIR_CANDIDATES = [
    Path("../imc-prosperity-4-main/ROUND1/ROUND_1"),
    Path("../../../imc-prosperity-4-main/ROUND1/ROUND_1"),
    Path("/Users/liam/local/brain/workspaces/imc-prosperity/imc-prosperity-4-main/ROUND1/ROUND_1"),
]


def _historical_dir() -> Path | None:
    for d in HISTORICAL_CSV_DIR_CANDIDATES:
        if d.exists():
            return d
    return None


def load_server_fv(path: Path) -> np.ndarray:
    data = json.loads(path.read_text())
    return np.array([t["fv"] for t in data["ticks"]], dtype=float)


def load_historical_mid_per_day(product: str) -> dict[int, np.ndarray]:
    """Returns mid_price series per day, with zero/NaN rows dropped (empty book)."""
    import pandas as pd
    out: dict[int, np.ndarray] = {}
    root = _historical_dir()
    if root is None:
        return out
    for day in (-2, -1):
        f = root / f"prices_round_1_day_{day}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, sep=";")
        df = df[df["product"] == product].sort_values("timestamp")
        mid = df["mid_price"].values.astype(float)
        mask = np.isfinite(mid) & (mid > 0)
        out[day] = mid[mask]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    fv = load_server_fv(FV_PATH)
    split = int(len(fv) * 0.67)
    train = fv[:split]
    heldout = fv[split:]
    choice = select_fv_model(train, heldout)
    posterior = bootstrap_posterior(train, choice.model)

    # cross-check with historical mid (per day, since concatenating across days
    # injects a fake discontinuity at the day boundary)
    hist_by_day = load_historical_mid_per_day(PRODUCT)
    hist_check = {}
    for day, series in hist_by_day.items():
        if len(series) < 10:
            continue
        hc = select_fv_model(series, None)
        hist_check[str(day)] = {
            "model": hc.model,
            "params": hc.params,
            "all_aic": hc.all_aic,
            "ljung_box_p": hc.residual_ljung_box_p,
            "n": int(len(series)),
            "mean": float(series.mean()),
            "std": float(series.std()),
        }
    if not hist_check:
        hist_check = None

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "product": PRODUCT,
        "model": choice.model,
        "params": choice.params,
        "aic": choice.aic,
        "held_out_ll": choice.held_out_ll,
        "residual_ljung_box_p": choice.residual_ljung_box_p,
        "all_aic": choice.all_aic,
        "all_held_out_ll": choice.all_held_out_ll,
        "all_ljung_box_p": choice.all_ljung_box_p,
        "posterior": {k: {"mean": v[0], "std": v[1]} for k, v in posterior.items()},
        "historical_mid_crosscheck": hist_check,
        "train_n": int(len(train)),
        "heldout_n": int(len(heldout)),
    }, indent=2))
    print(f"selected {choice.model} for {PRODUCT} (aic={choice.aic:.2f}, lb_p={choice.residual_ljung_box_p:.3f})")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
