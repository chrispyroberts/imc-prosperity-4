"""Parametric and non-parametric bootstrap for posterior construction."""
from __future__ import annotations

from typing import Callable

import numpy as np


def parametric_bootstrap(
    fit_fn: Callable[[np.ndarray], dict],
    simulate_fn: Callable[[dict, np.random.Generator, int], np.ndarray],
    fit_params: dict,
    n_bootstrap: int,
    n_samples: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Draws `n_bootstrap` resampled param sets by simulating under `fit_params`
    and re-fitting. Returns the list of re-fit param dicts.
    """
    out = []
    for _ in range(n_bootstrap):
        sim = simulate_fn(fit_params, rng, n_samples)
        out.append(fit_fn(sim))
    return out


def posterior_from_bootstrap(param_draws: list[dict], param_name: str) -> tuple[float, float]:
    """Returns (mean, std) of the bootstrap distribution of a single scalar param."""
    xs = np.array([d[param_name] for d in param_draws])
    return float(xs.mean()), float(xs.std(ddof=1))
