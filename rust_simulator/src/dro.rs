//! Distributionally Robust Optimization evaluation layer.
//!
//! For each MC session:
//! 1. Draw nominal params from the posterior (per ProductConfig).
//! 2. Draw K adversarial param sets from a widened posterior (std scaled by
//!    sqrt(1 + radius^2)).
//! 3. Simulate the strategy under each; record the minimum PnL.
//! 4. Aggregate across sessions to produce DroReport.

use crate::config::{ProductConfig, SampledProductParams};
use rand::Rng;
use serde::Serialize;
use std::collections::HashMap;

/// Per-session DRO breakdown, aggregated into `DroReport`.
#[derive(Clone, Debug, Serialize)]
pub struct DroSessionReport {
    pub session_id: usize,
    pub nominal_total_pnl: f64,
    pub worst_total_pnl: f64,
    pub per_product_nominal_pnl: HashMap<String, f64>,
    pub per_product_worst_pnl: HashMap<String, f64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct DroReport {
    pub radius: f64,
    pub k: usize,
    pub nominal_mean_pnl: f64,
    pub worst_case_mean_pnl: f64,
    pub worst_case_p05_pnl: f64,
    pub per_product_nominal_mean: HashMap<String, f64>,
    pub per_product_worst_mean: HashMap<String, f64>,
    pub sessions: Vec<DroSessionReport>,
}

/// Draws K adversarial parameter sets per session from a widened posterior.
pub fn sample_adversarial_params<R: Rng + ?Sized>(
    products: &[ProductConfig],
    radius: f64,
    k: usize,
    rng: &mut R,
) -> Vec<Vec<SampledProductParams>> {
    let widened: Vec<ProductConfig> = products.iter().map(|p| p.widen_posterior(radius)).collect();
    (0..k)
        .map(|_| widened.iter().map(|p| p.sample_from_posterior(rng)).collect())
        .collect()
}

/// Aggregates per-session DRO reports into final DroReport.
pub fn aggregate(sessions: Vec<DroSessionReport>, radius: f64, k: usize) -> DroReport {
    let n = sessions.len().max(1);
    let nominal_mean = sessions.iter().map(|s| s.nominal_total_pnl).sum::<f64>() / n as f64;
    let worst_mean = sessions.iter().map(|s| s.worst_total_pnl).sum::<f64>() / n as f64;
    let mut worst_sorted: Vec<f64> = sessions.iter().map(|s| s.worst_total_pnl).collect();
    worst_sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let p05 = worst_sorted.get((worst_sorted.len() / 20).max(0)).copied().unwrap_or(0.0);

    let mut per_product_nominal: HashMap<String, Vec<f64>> = HashMap::new();
    let mut per_product_worst: HashMap<String, Vec<f64>> = HashMap::new();
    for s in &sessions {
        for (k, v) in &s.per_product_nominal_pnl {
            per_product_nominal.entry(k.clone()).or_default().push(*v);
        }
        for (k, v) in &s.per_product_worst_pnl {
            per_product_worst.entry(k.clone()).or_default().push(*v);
        }
    }
    let avg = |m: HashMap<String, Vec<f64>>| -> HashMap<String, f64> {
        m.into_iter().map(|(k, vs)| {
            let m = vs.iter().sum::<f64>() / vs.len().max(1) as f64;
            (k, m)
        }).collect()
    };
    DroReport {
        radius,
        k,
        nominal_mean_pnl: nominal_mean,
        worst_case_mean_pnl: worst_mean,
        worst_case_p05_pnl: p05,
        per_product_nominal_mean: avg(per_product_nominal),
        per_product_worst_mean: avg(per_product_worst),
        sessions,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ProductConfig;
    use rand::SeedableRng;
    use rand_chacha::ChaCha8Rng;

    fn toy_product() -> ProductConfig {
        let src = r#"
            name = "X"
            position_limit = 80
            [fv_process]
            model = "fixed"
            price = 10000.0
            [bot1]
            bid_rule = "round_fv_minus_offset"
            ask_rule = "round_fv_plus_offset"
            offset   = 8.0
            volume   = { dist = "uniform_int", lo = 15, hi = 25 }
            [bot2]
            bid_rule = "round_fv_minus_offset"
            ask_rule = "round_fv_plus_offset"
            offset   = 6.0
            volume   = { dist = "uniform_int", lo = 5, hi = 10 }
            [bot3]
            presence_rate       = 0.05
            side_bid_prob       = 0.5
            price_delta_support = [-1, 0, 1]
            crossing_volume     = { dist = "uniform_int", lo = 3, hi = 8 }
            passive_volume      = { dist = "uniform_int", lo = 2, hi = 5 }
            [taker]
            trade_active_prob = { dist = "beta", alpha = 2, beta = 98 }
            second_trade_prob = 0.0
            buy_prob          = { dist = "beta", alpha = 5, beta = 5 }
        "#;
        toml::from_str(src).unwrap()
    }

    #[test]
    fn adversarial_samples_have_wider_spread_than_nominal() {
        let products = vec![toy_product()];
        let mut rng = ChaCha8Rng::seed_from_u64(1);
        let nominal: Vec<f64> = (0..500)
            .map(|_| products[0].sample_from_posterior(&mut rng).taker_buy_prob)
            .collect();
        let adv_batches = sample_adversarial_params(&products, 3.0, 500, &mut rng);
        let adv: Vec<f64> = adv_batches.iter().map(|b| b[0].taker_buy_prob).collect();
        assert!(variance(&adv) > variance(&nominal),
            "expected wider adversarial var, got nominal={} adv={}", variance(&nominal), variance(&adv));
    }

    #[test]
    fn aggregate_preserves_session_count_and_orders_mean() {
        let sessions = vec![
            DroSessionReport {
                session_id: 0,
                nominal_total_pnl: 100.0,
                worst_total_pnl: 50.0,
                per_product_nominal_pnl: [("A".into(), 100.0)].into_iter().collect(),
                per_product_worst_pnl: [("A".into(), 50.0)].into_iter().collect(),
            },
            DroSessionReport {
                session_id: 1,
                nominal_total_pnl: 200.0,
                worst_total_pnl: 60.0,
                per_product_nominal_pnl: [("A".into(), 200.0)].into_iter().collect(),
                per_product_worst_pnl: [("A".into(), 60.0)].into_iter().collect(),
            },
        ];
        let r = aggregate(sessions, 2.0, 3);
        assert_eq!(r.k, 3);
        assert_eq!(r.sessions.len(), 2);
        assert!((r.nominal_mean_pnl - 150.0).abs() < 1e-6);
        assert!((r.worst_case_mean_pnl - 55.0).abs() < 1e-6);
        // worst_case is, by definition, the min across k
        assert!(r.worst_case_mean_pnl <= r.nominal_mean_pnl);
    }

    fn variance(xs: &[f64]) -> f64 {
        let m: f64 = xs.iter().sum::<f64>() / xs.len() as f64;
        xs.iter().map(|x| (x - m).powi(2)).sum::<f64>() / xs.len() as f64
    }
}
