import numpy as np

from calibration.round1.lib.stats import chi_squared_uniform, z_test_binomial, ljung_box


def test_chi_squared_uniform_detects_real_structure():
    # 957/493 imbalance with n=1450 should be p ~ 0 per ANALYSIS_PHILOSOPHY.md
    observed = np.array([957, 493])
    p = chi_squared_uniform(observed)
    assert p < 1e-20, f"expected tiny p, got {p}"


def test_chi_squared_uniform_accepts_noise():
    # 55/45 split with n=242 should produce p near 0.14
    observed = np.array([133, 109])
    p = chi_squared_uniform(observed)
    assert 0.05 < p < 0.25, f"expected p~0.14, got {p}"


def test_z_test_binomial_rejects_real_structure():
    # buy_prob 195/399 vs null=0.5 => large p (consistent with 0.5)
    p = z_test_binomial(successes=195, n=399, p0=0.5)
    assert p > 0.4
    # 195/399 vs null=0.4 => significant
    p2 = z_test_binomial(successes=195, n=399, p0=0.4)
    assert p2 < 0.001


def test_ljung_box_accepts_white_noise():
    rng = np.random.default_rng(0)
    wn = rng.normal(0, 1, size=2000)
    p = ljung_box(wn, lags=20)
    assert p > 0.05
