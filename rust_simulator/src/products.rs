//! Per-product fair-value process step functions and bot-quote generation.
//! Dispatches on `SampledFvProcess` / rule strings from TOML.

use crate::config::SampledFvProcess;
use rand::Rng;
use rand_distr::{Distribution as RdDist, Normal};

/// Mutable state carried between ticks for a given product.
#[derive(Clone, Debug)]
pub struct FvState {
    pub current: f64,
}

impl FvState {
    pub fn initial(process: &SampledFvProcess) -> Self {
        let current = match process {
            SampledFvProcess::Fixed { price } => *price,
            SampledFvProcess::DriftingWalk { initial, .. } => *initial,
            SampledFvProcess::MeanRevertOU { center, .. } => *center,
        };
        FvState { current }
    }

    pub fn step<R: Rng + ?Sized>(&mut self, process: &SampledFvProcess, rng: &mut R) {
        match process {
            SampledFvProcess::Fixed { price } => self.current = *price,
            SampledFvProcess::DriftingWalk { drift, sigma, .. } => {
                let eps = Normal::new(0.0, *sigma).unwrap().sample(rng);
                self.current += *drift + eps;
            }
            SampledFvProcess::MeanRevertOU { center, kappa, sigma } => {
                let eps = Normal::new(0.0, *sigma).unwrap().sample(rng);
                self.current += -kappa * (self.current - center) + eps;
            }
        }
    }
}

/// Resolve a bot quote rule string to a concrete integer price given the
/// current fair value and an offset. Returns `None` for unknown rules.
pub fn quote_price_for_rule(rule: &str, fv: f64, offset: f64) -> Option<i32> {
    let fv_round = fv.round();
    let fv_floor = fv.floor();
    let fv_ceil = fv.ceil();
    let result = match rule {
        "round_fv_minus_offset" => fv_round - offset,
        "round_fv_plus_offset" => fv_round + offset,
        "floor_fv_minus_offset" => fv_floor - offset,
        "floor_fv_plus_offset" => fv_floor + offset,
        "ceil_fv_minus_offset" => fv_ceil - offset,
        "ceil_fv_plus_offset" => fv_ceil + offset,
        "floor_fv_plus_0_75_minus_offset" => (fv + 0.75).floor() - offset,
        "ceil_fv_plus_0_25_plus_offset" => (fv + 0.25).ceil() + offset,
        _ => return None,
    };
    Some(result as i32)
}

/// convenience: resolves both sides at once. panics on unknown rule.
pub fn quote_for_rule(bid_rule: &str, ask_rule: &str, fv: f64, offset: f64) -> (i32, i32) {
    (
        quote_price_for_rule(bid_rule, fv, offset).expect("known bid rule"),
        quote_price_for_rule(ask_rule, fv, offset).expect("known ask rule"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    #[test]
    fn fixed_stays_constant() {
        let p = SampledFvProcess::Fixed { price: 10000.0 };
        let mut s = FvState::initial(&p);
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        for _ in 0..100 {
            s.step(&p, &mut rng);
        }
        assert_eq!(s.current, 10000.0);
    }

    #[test]
    fn drifting_walk_variance_grows_linearly() {
        // zero-drift walk: empirical variance after N steps should be ~N*sigma^2
        let p = SampledFvProcess::DriftingWalk { initial: 0.0, drift: 0.0, sigma: 1.0 };
        let n_steps: usize = 100;
        let n_reps: usize = 2000;
        let mut rng = ChaCha8Rng::seed_from_u64(99);
        let mut finals = Vec::with_capacity(n_reps);
        for _ in 0..n_reps {
            let mut s = FvState::initial(&p);
            for _ in 0..n_steps {
                s.step(&p, &mut rng);
            }
            finals.push(s.current);
        }
        let mean: f64 = finals.iter().sum::<f64>() / (n_reps as f64);
        let var: f64 = finals.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n_reps as f64);
        assert!((var - (n_steps as f64)).abs() < (n_steps as f64) * 0.15, "var={}", var);
    }

    #[test]
    fn ou_half_life_approx_ln2_over_kappa() {
        // OU process with dt=1 and sigma=0 decays deterministically.
        let kappa = 0.2;
        let p = SampledFvProcess::MeanRevertOU { center: 100.0, kappa, sigma: 0.0 };
        let mut s = FvState::initial(&p);
        s.current = 200.0;
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        let expected_half_life = 2f64.ln() / -(1.0 - kappa).ln();
        let target: f64 = 100.0 + (200.0 - 100.0) / 2.0;
        let mut t = 0;
        while (s.current - 100.0).abs() > (target - 100.0).abs() {
            s.step(&p, &mut rng);
            t += 1;
        }
        let tf = t as f64;
        assert!((tf - expected_half_life).abs() < 1.0, "t={} expected={}", tf, expected_half_life);
    }

    #[test]
    fn bot1_symmetric_rule_round_fv_plus_minus_offset() {
        let (bid, ask) = quote_for_rule("round_fv_minus_offset", "round_fv_plus_offset", 10000.3, 8.0);
        assert_eq!(bid, 10000 - 8);
        assert_eq!(ask, 10000 + 8);
    }

    #[test]
    fn bot2_asymmetric_rounding_rules() {
        let (bid, ask) = quote_for_rule(
            "floor_fv_plus_0_75_minus_offset",
            "ceil_fv_plus_0_25_plus_offset",
            10000.5,
            7.0,
        );
        assert_eq!(bid, (10000.5f64 + 0.75).floor() as i32 - 7);
        assert_eq!(ask, (10000.5f64 + 0.25).ceil() as i32 + 7);
    }

    #[test]
    fn unknown_rule_returns_none() {
        let res = quote_price_for_rule("nonsense_rule", 10000.0, 8.0);
        assert!(res.is_none());
    }
}
