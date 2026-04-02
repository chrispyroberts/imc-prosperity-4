from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "round0"


def load_tomatoes() -> pd.DataFrame:
    frames = []
    for day in (-2, -1):
        df = pd.read_csv(DATA_DIR / f"prices_round_0_day_{day}.csv", sep=";")
        df = df[df["product"] == "TOMATOES"].copy().sort_values("timestamp")
        bid_cols = [f"bid_price_{i}" for i in (1, 2, 3)]
        ask_cols = [f"ask_price_{i}" for i in (1, 2, 3)]
        df["fair"] = (df[bid_cols].min(axis=1) + df[ask_cols].max(axis=1)) / 2
        df["ret"] = df["fair"].diff()
        df["day"] = day
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def variance_ratio(series: pd.Series, k: int) -> float:
    ret1 = series.diff().dropna()
    v1 = ret1.var()
    vk = series.diff(k).dropna().var()
    return vk / (k * v1)


def fit_ar1_returns(returns: pd.Series) -> dict[str, float]:
    r = returns.dropna().to_numpy()
    x = r[:-1]
    y = r[1:]
    denom = np.dot(x, x)
    phi = float(np.dot(x, y) / denom) if denom > 0 else 0.0
    eps = y - phi * x
    sigma_eps = float(eps.std(ddof=1))
    unconditional_var = float(r.var(ddof=1))
    implied_uncond = sigma_eps**2 / (1 - phi**2) if abs(phi) < 1 else math.nan
    sign_flip = float(np.mean(np.sign(y[x != 0]) != np.sign(x[x != 0]))) if np.any(x != 0) else math.nan
    return {
        "phi": phi,
        "sigma_eps": sigma_eps,
        "unconditional_std": math.sqrt(unconditional_var),
        "implied_unconditional_std": math.sqrt(implied_uncond) if implied_uncond >= 0 else math.nan,
        "sign_flip_prob": sign_flip,
    }


def realized_variance_blocks(returns: pd.Series, block: int) -> pd.DataFrame:
    r2 = returns.fillna(0.0).pow(2).to_numpy()
    usable = len(r2) // block * block
    r2 = r2[:usable]
    rv = r2.reshape(-1, block).sum(axis=1)
    out = pd.DataFrame({"rv": rv})
    out["rv_lag1"] = out["rv"].shift(1)
    return out


def gamma_mom_fit(values: pd.Series) -> dict[str, float]:
    x = values.dropna().to_numpy()
    mean = float(x.mean())
    var = float(x.var(ddof=1))
    shape = mean**2 / var if var > 0 else math.nan
    scale = var / mean if mean > 0 else math.nan
    return {"mean": mean, "std": math.sqrt(var), "shape": shape, "scale": scale}


def print_return_stats(df: pd.DataFrame) -> None:
    print("\n=== Return Law ===")
    for day, sub in df.groupby("day"):
        ret = sub["ret"].dropna()
        abs_ret = ret.abs()
        vc = ret.value_counts(normalize=True).sort_index()
        print(f"\nDay {day}")
        print(f"  FV start/end: {sub['fair'].iloc[0]:.1f} -> {sub['fair'].iloc[-1]:.1f}")
        print(f"  FV range/std: [{sub['fair'].min():.1f}, {sub['fair'].max():.1f}] / {sub['fair'].std():.4f}")
        print(f"  Return mean/std: {ret.mean():+.6f} / {ret.std():.6f}")
        print(f"  P(|ret|=0.0) = {(abs_ret == 0).mean():.4f}")
        print(f"  P(|ret|=0.5) = {(abs_ret == 0.5).mean():.4f}")
        print(f"  P(|ret|=1.0) = {(abs_ret == 1.0).mean():.4f}")
        print(f"  P(|ret|=1.5) = {(abs_ret == 1.5).mean():.4f}")
        print(f"  P(|ret|=2.0) = {(abs_ret == 2.0).mean():.4f}")
        print(f"  Full return distribution: { {float(k): round(v, 4) for k, v in vc.items()} }")


def print_markov_stats(df: pd.DataFrame) -> None:
    print("\n=== Step / Sign Dynamics ===")
    for day, sub in df.groupby("day"):
        ret = sub["ret"].dropna().reset_index(drop=True)
        prev = ret.shift(1)
        valid = pd.DataFrame({"prev": prev, "ret": ret}).dropna()
        nonzero = valid[valid["prev"] != 0].copy()
        sign_prev = np.sign(nonzero["prev"])
        sign_now = np.sign(nonzero["ret"])
        same_sign = (sign_prev == sign_now).mean()
        flip_sign = (sign_prev == -sign_now).mean()
        hit_zero = (sign_now == 0).mean()
        print(f"\nDay {day}")
        print(f"  ACF lag1 ret: {ret.autocorr(lag=1):+.4f}")
        print(f"  Same sign | prev nonzero: {same_sign:.4f}")
        print(f"  Flip sign | prev nonzero: {flip_sign:.4f}")
        print(f"  Hit zero  | prev nonzero: {hit_zero:.4f}")
        ar1 = fit_ar1_returns(ret)
        print(f"  AR(1) phi on returns: {ar1['phi']:+.4f}")
        print(f"  AR(1) sigma_eps: {ar1['sigma_eps']:.4f}")
        print(f"  AR(1) implied uncond std: {ar1['implied_unconditional_std']:.4f}")


def print_variance_ratio_stats(df: pd.DataFrame) -> None:
    print("\n=== Variance Ratios ===")
    for day, sub in df.groupby("day"):
        fv = sub["fair"].reset_index(drop=True)
        print(f"\nDay {day}")
        for k in (2, 5, 10, 20, 50, 100):
            print(f"  VR({k:3d}) = {variance_ratio(fv, k):.4f}")


def print_realized_variance_fit(df: pd.DataFrame) -> None:
    print("\n=== Realized Variance Fit ===")
    for day, sub in df.groupby("day"):
        ret = sub["ret"].dropna().reset_index(drop=True)
        print(f"\nDay {day}")
        for block in (10, 20, 50, 100, 200):
            rv = realized_variance_blocks(ret, block)
            fit = gamma_mom_fit(rv["rv"])
            ac1 = rv["rv"].autocorr(lag=1)
            print(
                f"  block={block:3d}  mean={fit['mean']:.4f}  std={fit['std']:.4f}  "
                f"shape={fit['shape']:.3f}  scale={fit['scale']:.4f}  ac1={ac1:+.4f}"
            )


def print_combined_fit(df: pd.DataFrame) -> None:
    ret = df["ret"].dropna().reset_index(drop=True)
    abs_ret = ret.abs()
    ar1 = fit_ar1_returns(ret)
    print("\n=== Combined Parameter Estimate For Simulator ===")
    print(f"Return support: {sorted(ret.unique().tolist())}")
    print("Magnitude probabilities:")
    for level in (0.0, 0.5, 1.0, 1.5, 2.0):
        print(f"  P(|ret|={level:.1f}) = {(abs_ret == level).mean():.4f}")
    print(f"AR(1) phi on returns: {ar1['phi']:+.4f}")
    print(f"AR(1) sigma_eps: {ar1['sigma_eps']:.4f}")
    print(f"Unconditional ret std: {ar1['unconditional_std']:.4f}")
    print(f"Sign flip prob | prev nonzero: {ar1['sign_flip_prob']:.4f}")
    print("\nSuggested simple simulator target:")
    print("  r_t = phi * r_{t-1} + eps_t  on a latent half-tick process")
    print("  then quantize to support {0, +-0.5, +-1.0, +-1.5, +-2.0}")
    print("  with phi near -0.18 and innovation scale near 0.61")


def main() -> None:
    df = load_tomatoes()
    print_return_stats(df)
    print_markov_stats(df)
    print_variance_ratio_stats(df)
    print_realized_variance_fit(df)
    print_combined_fit(df)


if __name__ == "__main__":
    main()
