//! Draws concrete parameter values from the `Distribution` specs in a loaded
//! `SimConfig`. Called once per MC session so sessions reflect parameter
//! uncertainty in addition to path stochasticity.

use crate::config::{Distribution, ParametricDist};
use rand::Rng;
use rand_distr::{Beta, Distribution as RdDist, LogNormal, Normal};

impl Distribution {
    /// Sample a concrete float value from this distribution spec.
    /// `Fixed(x)` returns `x` deterministically.
    pub fn sample<R: Rng + ?Sized>(&self, rng: &mut R) -> f64 {
        match self {
            Distribution::Fixed(x) => *x,
            Distribution::Parametric(p) => p.sample(rng),
        }
    }

    /// Sample an integer value; used for volume ranges and count params.
    pub fn sample_int<R: Rng + ?Sized>(&self, rng: &mut R) -> i64 {
        match self {
            Distribution::Fixed(x) => x.round() as i64,
            Distribution::Parametric(ParametricDist::UniformInt { lo, hi }) => {
                rng.gen_range(*lo..=*hi)
            }
            other => other.sample(rng).round() as i64,
        }
    }
}

impl ParametricDist {
    pub fn sample<R: Rng + ?Sized>(&self, rng: &mut R) -> f64 {
        match self {
            ParametricDist::Normal { mean, std } => {
                Normal::new(*mean, *std).expect("valid normal").sample(rng)
            }
            ParametricDist::Lognormal { mu, sigma } => {
                LogNormal::new(*mu, *sigma).expect("valid lognormal").sample(rng)
            }
            ParametricDist::UniformInt { lo, hi } => rng.gen_range(*lo..=*hi) as f64,
            ParametricDist::UniformFloat { lo, hi } => rng.gen_range(*lo..*hi),
            ParametricDist::Beta { alpha, beta } => {
                Beta::new(*alpha, *beta).expect("valid beta").sample(rng)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn fixed_distribution_returns_exact_value() {
        let d = Distribution::Fixed(42.0);
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        for _ in 0..10 {
            assert_eq!(d.sample(&mut rng), 42.0);
        }
    }

    #[test]
    fn normal_empirical_mean_within_tolerance() {
        let d = Distribution::Parametric(ParametricDist::Normal { mean: 3.0, std: 1.0 });
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        let draws: Vec<f64> = (0..10_000).map(|_| d.sample(&mut rng)).collect();
        let mean: f64 = draws.iter().sum::<f64>() / draws.len() as f64;
        assert!((mean - 3.0).abs() < 0.05, "mean={}", mean);
    }

    #[test]
    fn beta_in_unit_interval() {
        let d = Distribution::Parametric(ParametricDist::Beta { alpha: 2.0, beta: 5.0 });
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        for _ in 0..1000 {
            let x = d.sample(&mut rng);
            assert!((0.0..=1.0).contains(&x), "x={}", x);
        }
    }

    #[test]
    fn uniform_int_respects_bounds() {
        let d = Distribution::Parametric(ParametricDist::UniformInt { lo: 5, hi: 10 });
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        for _ in 0..500 {
            let x = d.sample_int(&mut rng);
            assert!((5..=10).contains(&x), "x={}", x);
        }
    }

    #[test]
    fn sampling_is_deterministic_under_same_seed() {
        let d = Distribution::Parametric(ParametricDist::Normal { mean: 0.0, std: 1.0 });
        let mut r1 = ChaCha8Rng::seed_from_u64(42);
        let mut r2 = ChaCha8Rng::seed_from_u64(42);
        for _ in 0..50 {
            assert_eq!(d.sample(&mut r1), d.sample(&mut r2));
        }
    }

    #[test]
    fn product_config_samples_consistent_types() {
        use crate::config::*;
        let toml_src = r#"
            name = "X"
            position_limit = 80

            [fv_process]
            model = "mean_revert_ou"
            center = 10000.0
            kappa  = { dist = "normal", mean = 0.015, std = 0.004 }
            sigma  = { dist = "lognormal", mu = -0.7, sigma = 0.15 }

            [bot1]
            bid_rule = "round_fv_minus_offset"
            ask_rule = "round_fv_plus_offset"
            offset   = 10.0
            volume   = { dist = "uniform_int", lo = 20, hi = 30 }

            [bot2]
            bid_rule = "round_fv_minus_offset"
            ask_rule = "round_fv_plus_offset"
            offset   = 8.0
            volume   = { dist = "uniform_int", lo = 8, hi = 15 }

            [bot3]
            presence_rate       = 0.06
            side_bid_prob       = 0.5
            price_delta_support = [-1, 0, 1]
            crossing_volume     = { dist = "uniform_int", lo = 5, hi = 12 }
            passive_volume      = { dist = "uniform_int", lo = 2, hi = 6 }

            [taker]
            trade_active_prob = 0.02
            second_trade_prob = 0.001
            buy_prob          = 0.5
        "#;
        let cfg: ProductConfig = toml::from_str(toml_src).unwrap();
        let mut rng = ChaCha8Rng::seed_from_u64(7);
        let s = cfg.sample_from_posterior(&mut rng);
        assert_eq!(s.position_limit, 80);
        assert!((20..=30).contains(&s.bot1_volume_lo));
        assert!(s.bot1_volume_hi >= s.bot1_volume_lo);
        assert!((0.0..=1.0).contains(&s.taker_buy_prob));
        match s.fv_process {
            SampledFvProcess::MeanRevertOU { center, .. } => assert!((center - 10000.0).abs() < 1e-6),
            _ => panic!("expected OU"),
        }
    }
}
