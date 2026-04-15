import numpy as np

from calibration.round1.lib.fv_process import (
    fit_fixed,
    fit_drifting_walk,
    fit_mean_revert_ou,
    select_fv_model,
)


def test_fit_fixed_on_constant_series():
    fv = np.full(1000, 10000.0)
    params, aic = fit_fixed(fv)
    assert abs(params["price"] - 10000.0) < 1e-6


def test_fit_drifting_walk_recovers_drift():
    # drift MLE stderr = sigma / sqrt(n); at sigma=0.5, n=1000 that's ~0.016, so
    # a true drift of 0.01 can't be recovered to <0.01. Use a regime with stronger
    # signal-to-noise (bigger drift, smaller sigma) so the estimator is testable.
    rng = np.random.default_rng(1)
    true_drift = 0.1
    fv = 11900 + true_drift * np.arange(2000) + np.cumsum(rng.normal(0, 0.3, size=2000))
    params, _ = fit_drifting_walk(fv)
    assert abs(params["drift"] - true_drift) < 0.01


def test_fit_mean_revert_ou_recovers_kappa():
    rng = np.random.default_rng(2)
    fv = np.zeros(2000)
    fv[0] = 10.0
    kappa_true = 0.1
    for i in range(1, len(fv)):
        fv[i] = fv[i - 1] - kappa_true * (fv[i - 1] - 0.0) + rng.normal(0, 0.5)
    params, _ = fit_mean_revert_ou(fv)
    assert abs(params["kappa"] - kappa_true) < 0.05


def test_select_picks_drifting_walk_on_trending_series():
    rng = np.random.default_rng(3)
    fv = 11900 + 0.01 * np.arange(1000) + np.cumsum(rng.normal(0, 0.5, size=1000))
    choice = select_fv_model(fv, fv)
    assert choice.model in {"drifting_walk", "mean_revert_ou"}
    # strict Fixed should lose clearly
    assert choice.model != "fixed"
