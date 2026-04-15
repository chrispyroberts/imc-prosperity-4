"""Empirical CDF utilities.

Per ANALYSIS_PHILOSOPHY: some distributions (e.g., taker volume mixes)
are modeled empirically rather than forced into parametric families.
"""
from __future__ import annotations

import numpy as np


def empirical_cdf(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (sorted_values, cumulative_probs)."""
    sv = np.sort(np.asarray(values))
    cp = np.arange(1, len(sv) + 1) / len(sv)
    return sv, cp


def sample_from_empirical(sorted_values: np.ndarray, rng: np.random.Generator, k: int = 1) -> np.ndarray:
    idx = rng.integers(0, len(sorted_values), size=k)
    return sorted_values[idx]
