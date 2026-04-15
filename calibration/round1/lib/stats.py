"""Statistical tests used by all calibration scripts.

Every calibration claim about uniformity, symmetry, or residual whiteness
runs through one of these. Per ANALYSIS_PHILOSOPHY.md: never hardcode from
eyeballs; always cite the p-value.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def chi_squared_uniform(observed: np.ndarray) -> float:
    """Two-sided chi-squared test that `observed` counts come from a uniform
    distribution over len(observed) categories. Returns the p-value.
    """
    observed = np.asarray(observed, dtype=float)
    expected = np.full_like(observed, observed.sum() / len(observed))
    _, p = stats.chisquare(observed, expected)
    return float(p)


def z_test_binomial(successes: int, n: int, p0: float) -> float:
    """Two-sided z-test for binomial proportion vs null p0. Returns p-value."""
    p_hat = successes / n
    se = (p0 * (1 - p0) / n) ** 0.5
    z = (p_hat - p0) / se if se > 0 else 0.0
    return 2.0 * (1.0 - stats.norm.cdf(abs(z)))


def ljung_box(residuals: np.ndarray, lags: int = 20) -> float:
    """Returns Ljung-Box p-value for residual whiteness at the given lags.
    p > 0.05 => residuals indistinguishable from white noise.
    """
    from scipy.stats import chi2
    r = np.asarray(residuals, dtype=float)
    r = r - r.mean()
    n = len(r)
    acf = np.correlate(r, r, mode="full")[n - 1 :]
    acf = acf / acf[0]
    q = n * (n + 2) * sum(acf[k] ** 2 / (n - k) for k in range(1, lags + 1))
    return float(1.0 - chi2.cdf(q, df=lags))
