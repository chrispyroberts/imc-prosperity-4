"""FV-process model fitting and selection.

Three candidate processes:
  Fixed:         x_t = c + eps
  DriftingWalk:  x_{t+1} = x_t + drift + eps,   eps ~ N(0, sigma^2)
  MeanRevertOU:  x_{t+1} = x_t - kappa*(x_t - center) + eps

For each, we return ML point estimates, AIC, and held-out gaussian log-likelihood
on the one-step-ahead predictive distribution. select_fv_model ranks by held-out
LL (falls back to AIC when no held-out is supplied).

Residual diagnostic uses Ljung-Box on one-step standardized residuals: p>0.05
means the residuals are indistinguishable from white noise so the chosen
process captures the autocorrelation structure.

bootstrap_posterior does a non-parametric block-free bootstrap on the
increments (Fixed resamples levels; DriftingWalk and OU resample innovations
reconstructed from the path). Returns per-param (mean, std) useful for
emitting posterior distributions into round1.toml.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
from scipy import optimize

from calibration.round1.lib.stats import ljung_box


# ---------- gaussian log-likelihood helpers ----------

def _gauss_ll(resid: np.ndarray, sigma: float) -> float:
    n = len(resid)
    if sigma <= 0:
        return -np.inf
    return float(-0.5 * n * np.log(2 * np.pi * sigma * sigma) - 0.5 * np.sum(resid * resid) / (sigma * sigma))


def _aic(ll: float, k: int) -> float:
    return float(2 * k - 2 * ll)


# ---------- per-model fitters ----------

def fit_fixed(fv: np.ndarray) -> tuple[dict, float]:
    """MLE fit of a constant-mean gaussian. Residuals = fv - mean(fv)."""
    fv = np.asarray(fv, dtype=float)
    mu = float(fv.mean())
    resid = fv - mu
    n = len(fv)
    # MLE sigma (biased); handle degenerate constant series
    var = float((resid * resid).mean())
    sigma = max(np.sqrt(var), 1e-9)
    ll = _gauss_ll(resid, sigma)
    params = {"price": mu, "sigma": sigma}
    return params, _aic(ll, k=2)


def fit_drifting_walk(fv: np.ndarray) -> tuple[dict, float]:
    """MLE fit of a random walk with drift. Innovations = diff(fv) - drift."""
    fv = np.asarray(fv, dtype=float)
    diffs = np.diff(fv)
    drift = float(diffs.mean())
    innov = diffs - drift
    sigma = max(float(np.sqrt((innov * innov).mean())), 1e-9)
    ll = _gauss_ll(innov, sigma)
    params = {"initial": float(fv[0]), "drift": drift, "sigma": sigma}
    return params, _aic(ll, k=3)


def fit_mean_revert_ou(fv: np.ndarray) -> tuple[dict, float]:
    """MLE fit of discrete OU: x_{t+1} = x_t - kappa*(x_t - center) + N(0, sigma^2).

    Rearranges to diff = -kappa * (x - center) + eps, i.e. a linear regression
    of diff on x with slope -kappa and intercept +kappa*center. Closed-form OLS.
    """
    fv = np.asarray(fv, dtype=float)
    x = fv[:-1]
    diffs = np.diff(fv)
    # linear regression: diffs = a + b*x; then kappa = -b, center = a / kappa (if kappa != 0)
    x_mean = x.mean()
    d_mean = diffs.mean()
    cov = float(((x - x_mean) * (diffs - d_mean)).sum())
    var_x = float(((x - x_mean) ** 2).sum())
    if var_x <= 0:
        # degenerate path, fall back to zero-kappa
        slope = 0.0
        intercept = d_mean
    else:
        slope = cov / var_x
        intercept = d_mean - slope * x_mean
    kappa = float(-slope)
    # guard against nonsensical kappa (MLE can give slightly negative or >1 on short series)
    if abs(kappa) < 1e-9:
        center = float(x_mean)
    else:
        center = float(-intercept / slope) if slope != 0 else float(x_mean)
    resid = diffs - (intercept + slope * x)
    sigma = max(float(np.sqrt((resid * resid).mean())), 1e-9)
    ll = _gauss_ll(resid, sigma)
    params = {"center": center, "kappa": kappa, "sigma": sigma, "initial": float(fv[0])}
    return params, _aic(ll, k=4)


# ---------- held-out log-likelihood ----------

def held_out_ll_fixed(params: dict, fv_heldout: np.ndarray) -> float:
    resid = np.asarray(fv_heldout, dtype=float) - params["price"]
    return _gauss_ll(resid, params["sigma"])


def held_out_ll_drifting_walk(params: dict, fv_heldout: np.ndarray) -> float:
    fv = np.asarray(fv_heldout, dtype=float)
    if len(fv) < 2:
        return 0.0
    innov = np.diff(fv) - params["drift"]
    return _gauss_ll(innov, params["sigma"])


def held_out_ll_mean_revert_ou(params: dict, fv_heldout: np.ndarray) -> float:
    fv = np.asarray(fv_heldout, dtype=float)
    if len(fv) < 2:
        return 0.0
    x = fv[:-1]
    predicted_delta = -params["kappa"] * (x - params["center"])
    resid = np.diff(fv) - predicted_delta
    return _gauss_ll(resid, params["sigma"])


# ---------- residual diagnostic ----------

def residual_diagnostic(model: str, params: dict, fv: np.ndarray, lags: int = 20) -> float:
    """Returns Ljung-Box p-value on one-step standardized residuals."""
    fv = np.asarray(fv, dtype=float)
    if model == "fixed":
        resid = fv - params["price"]
    elif model == "drifting_walk":
        if len(fv) < 2:
            return 1.0
        resid = np.diff(fv) - params["drift"]
    elif model == "mean_revert_ou":
        if len(fv) < 2:
            return 1.0
        x = fv[:-1]
        resid = np.diff(fv) - (-params["kappa"] * (x - params["center"]))
    else:
        raise ValueError(f"unknown model {model}")
    return ljung_box(resid, lags=lags)


# ---------- model selection ----------

@dataclass
class ModelChoice:
    model: str
    params: dict
    aic: float
    held_out_ll: Optional[float]
    residual_ljung_box_p: float
    all_aic: dict
    all_held_out_ll: dict
    all_ljung_box_p: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


_FITTERS = {
    "fixed": (fit_fixed, held_out_ll_fixed),
    "drifting_walk": (fit_drifting_walk, held_out_ll_drifting_walk),
    "mean_revert_ou": (fit_mean_revert_ou, held_out_ll_mean_revert_ou),
}


def select_fv_model(fv_train: np.ndarray, fv_heldout: Optional[np.ndarray] = None) -> ModelChoice:
    """Fits all three candidates on fv_train. If fv_heldout is provided, ranks by
    held-out LL; else ranks by AIC. Returns the winning ModelChoice plus the
    scoreboard across all candidates.
    """
    fv_train = np.asarray(fv_train, dtype=float)
    fits: dict[str, tuple[dict, float]] = {}
    held: dict[str, Optional[float]] = {}
    lb: dict[str, float] = {}
    for name, (fit_fn, ho_fn) in _FITTERS.items():
        params, aic = fit_fn(fv_train)
        fits[name] = (params, aic)
        held[name] = ho_fn(params, fv_heldout) if fv_heldout is not None and len(fv_heldout) > 0 else None
        lb[name] = residual_diagnostic(name, params, fv_train)

    # rank: prefer held-out LL (higher is better), else AIC (lower is better)
    if fv_heldout is not None and len(fv_heldout) > 0:
        best = max(fits.keys(), key=lambda n: held[n])
    else:
        best = min(fits.keys(), key=lambda n: fits[n][1])

    params, aic = fits[best]
    return ModelChoice(
        model=best,
        params=params,
        aic=aic,
        held_out_ll=held[best],
        residual_ljung_box_p=lb[best],
        all_aic={n: fits[n][1] for n in fits},
        all_held_out_ll=held,
        all_ljung_box_p=lb,
    )


# ---------- bootstrap posterior ----------

def bootstrap_posterior(
    fv: np.ndarray,
    model: str,
    n_boot: int = 500,
    rng: Optional[np.random.Generator] = None,
) -> dict[str, tuple[float, float]]:
    """Non-parametric bootstrap of the chosen process's parameters.

    For Fixed we resample the levels. For DriftingWalk we resample first-differences
    and reconstruct a path, then re-fit. For MeanRevertOU we resample innovations
    from the fitted residuals and re-simulate forward from fv[0].
    """
    fv = np.asarray(fv, dtype=float)
    if rng is None:
        rng = np.random.default_rng(0)

    draws: list[dict] = []
    if model == "fixed":
        n = len(fv)
        for _ in range(n_boot):
            idx = rng.integers(0, n, size=n)
            sim = fv[idx]
            params, _ = fit_fixed(sim)
            draws.append(params)
    elif model == "drifting_walk":
        diffs = np.diff(fv)
        n = len(diffs)
        x0 = float(fv[0])
        for _ in range(n_boot):
            sample = diffs[rng.integers(0, n, size=n)]
            sim = np.concatenate([[x0], x0 + np.cumsum(sample)])
            params, _ = fit_drifting_walk(sim)
            draws.append(params)
    elif model == "mean_revert_ou":
        point, _ = fit_mean_revert_ou(fv)
        kappa = point["kappa"]
        center = point["center"]
        x = fv[:-1]
        resid = np.diff(fv) - (-kappa * (x - center))
        n = len(resid)
        x0 = float(fv[0])
        for _ in range(n_boot):
            innov = resid[rng.integers(0, n, size=n)]
            sim = np.empty(n + 1)
            sim[0] = x0
            for t in range(n):
                sim[t + 1] = sim[t] - kappa * (sim[t] - center) + innov[t]
            params, _ = fit_mean_revert_ou(sim)
            draws.append(params)
    else:
        raise ValueError(f"unknown model {model}")

    keys = draws[0].keys()
    summary: dict[str, tuple[float, float]] = {}
    for k in keys:
        xs = np.array([d[k] for d in draws])
        summary[k] = (float(xs.mean()), float(xs.std(ddof=1)))
    return summary


# convenience
__all__ = [
    "fit_fixed",
    "fit_drifting_walk",
    "fit_mean_revert_ou",
    "held_out_ll_fixed",
    "held_out_ll_drifting_walk",
    "held_out_ll_mean_revert_ou",
    "residual_diagnostic",
    "select_fv_model",
    "bootstrap_posterior",
    "ModelChoice",
]
