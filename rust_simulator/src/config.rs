//! TOML-driven configuration for the Monte Carlo simulator.
//! Product list, FV processes, bot quote rules, taker parameters,
//! and posterior distributions all live here (not in `main.rs`).

use serde::{Deserialize, Serialize};

/// Top-level TOML document. Emitted by `calibration/round1/scripts/emit_config.py`
/// and loaded at simulator startup via `toml::from_str`.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SimConfig {
    pub meta: Meta,
    #[serde(default)]
    pub products: Vec<ProductConfig>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Meta {
    pub round: u32,
    pub ticks_per_day: usize,
    pub shared_position_limit: i32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProductConfig {
    pub name: String,
    pub position_limit: i32,
    pub fv_process: FairValueModel,
    pub bot1: Bot1Params,
    pub bot2: Bot2Params,
    pub bot3: Bot3Params,
    pub taker: TakerParams,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "model", rename_all = "snake_case")]
pub enum FairValueModel {
    Fixed { price: Distribution },
    DriftingWalk { initial: Distribution, drift: Distribution, sigma: Distribution },
    #[serde(rename = "mean_revert_ou")]
    MeanRevertOU { center: Distribution, kappa: Distribution, sigma: Distribution },
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Bot1Params {
    pub bid_rule: String,
    pub ask_rule: String,
    pub offset: Distribution,
    pub volume: Distribution,
    #[serde(default = "default_presence")]
    pub presence_rate: Distribution,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Bot2Params {
    pub bid_rule: String,
    pub ask_rule: String,
    pub offset: Distribution,
    pub volume: Distribution,
    #[serde(default = "default_presence")]
    pub presence_rate: Distribution,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Bot3Params {
    pub presence_rate: Distribution,
    pub side_bid_prob: Distribution,
    pub price_delta_support: Vec<i32>,
    pub crossing_volume: Distribution,
    pub passive_volume: Distribution,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct TakerParams {
    pub trade_active_prob: Distribution,
    pub second_trade_prob: Distribution,
    pub buy_prob: Distribution,
}

fn default_presence() -> Distribution {
    Distribution::Fixed(1.0)
}

/// Concrete parameter values drawn from `ProductConfig`'s posteriors.
/// Session loop runs against this struct.
#[derive(Clone, Debug)]
pub struct SampledProductParams {
    pub name: String,
    pub position_limit: i32,
    pub fv_process: SampledFvProcess,
    pub bot1_offset: f64,
    pub bot1_volume_lo: i64,
    pub bot1_volume_hi: i64,
    pub bot1_presence: f64,
    pub bot1_bid_rule: String,
    pub bot1_ask_rule: String,
    pub bot2_offset: f64,
    pub bot2_volume_lo: i64,
    pub bot2_volume_hi: i64,
    pub bot2_presence: f64,
    pub bot2_bid_rule: String,
    pub bot2_ask_rule: String,
    pub bot3_presence: f64,
    pub bot3_side_bid_prob: f64,
    pub bot3_price_delta_support: Vec<i32>,
    pub bot3_crossing_volume_lo: i64,
    pub bot3_crossing_volume_hi: i64,
    pub bot3_passive_volume_lo: i64,
    pub bot3_passive_volume_hi: i64,
    pub taker_trade_active_prob: f64,
    pub taker_second_trade_prob: f64,
    pub taker_buy_prob: f64,
}

#[derive(Clone, Debug)]
pub enum SampledFvProcess {
    Fixed { price: f64 },
    DriftingWalk { initial: f64, drift: f64, sigma: f64 },
    MeanRevertOU { center: f64, kappa: f64, sigma: f64 },
}

/// a parameter value in TOML: either a fixed scalar or a parametric family
/// that gets sampled per session by `posterior.rs`.
///
/// the `#[serde(untagged)]` representation accepts both `x = 3.14` and
/// `x = { dist = "normal", mean = 0.0, std = 1.0 }` in the same field.
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(untagged)]
pub enum Distribution {
    Fixed(f64),
    Parametric(ParametricDist),
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "dist", rename_all = "snake_case")]
pub enum ParametricDist {
    Normal { mean: f64, std: f64 },
    Lognormal { mu: f64, sigma: f64 },
    UniformInt { lo: i64, hi: i64 },
    UniformFloat { lo: f64, hi: f64 },
    Beta { alpha: f64, beta: f64 },
}

impl ProductConfig {
    pub fn sample_from_posterior<R: rand::Rng + ?Sized>(&self, rng: &mut R) -> SampledProductParams {
        let (b1_lo, b1_hi) = sample_uniform_int_pair(&self.bot1.volume, rng);
        let (b2_lo, b2_hi) = sample_uniform_int_pair(&self.bot2.volume, rng);
        let (b3x_lo, b3x_hi) = sample_uniform_int_pair(&self.bot3.crossing_volume, rng);
        let (b3p_lo, b3p_hi) = sample_uniform_int_pair(&self.bot3.passive_volume, rng);
        SampledProductParams {
            name: self.name.clone(),
            position_limit: self.position_limit,
            fv_process: sample_fv(&self.fv_process, rng),
            bot1_offset: self.bot1.offset.sample(rng),
            bot1_volume_lo: b1_lo,
            bot1_volume_hi: b1_hi,
            bot1_presence: self.bot1.presence_rate.sample(rng).clamp(0.0, 1.0),
            bot1_bid_rule: self.bot1.bid_rule.clone(),
            bot1_ask_rule: self.bot1.ask_rule.clone(),
            bot2_offset: self.bot2.offset.sample(rng),
            bot2_volume_lo: b2_lo,
            bot2_volume_hi: b2_hi,
            bot2_presence: self.bot2.presence_rate.sample(rng).clamp(0.0, 1.0),
            bot2_bid_rule: self.bot2.bid_rule.clone(),
            bot2_ask_rule: self.bot2.ask_rule.clone(),
            bot3_presence: self.bot3.presence_rate.sample(rng).clamp(0.0, 1.0),
            bot3_side_bid_prob: self.bot3.side_bid_prob.sample(rng).clamp(0.0, 1.0),
            bot3_price_delta_support: self.bot3.price_delta_support.clone(),
            bot3_crossing_volume_lo: b3x_lo,
            bot3_crossing_volume_hi: b3x_hi,
            bot3_passive_volume_lo: b3p_lo,
            bot3_passive_volume_hi: b3p_hi,
            taker_trade_active_prob: self.taker.trade_active_prob.sample(rng).clamp(0.0, 1.0),
            taker_second_trade_prob: self.taker.second_trade_prob.sample(rng).clamp(0.0, 1.0),
            taker_buy_prob: self.taker.buy_prob.sample(rng).clamp(0.0, 1.0),
        }
    }
}

fn sample_fv<R: rand::Rng + ?Sized>(fv: &FairValueModel, rng: &mut R) -> SampledFvProcess {
    match fv {
        FairValueModel::Fixed { price } => SampledFvProcess::Fixed { price: price.sample(rng) },
        FairValueModel::DriftingWalk { initial, drift, sigma } => SampledFvProcess::DriftingWalk {
            initial: initial.sample(rng),
            drift: drift.sample(rng),
            sigma: sigma.sample(rng).max(1e-9),
        },
        FairValueModel::MeanRevertOU { center, kappa, sigma } => SampledFvProcess::MeanRevertOU {
            center: center.sample(rng),
            kappa: kappa.sample(rng).max(0.0),
            sigma: sigma.sample(rng).max(1e-9),
        },
    }
}

/// For UniformInt distributions we take lo and hi as-is. For any other shape,
/// we draw two samples and order them so lo <= hi.
fn sample_uniform_int_pair<R: rand::Rng + ?Sized>(d: &Distribution, rng: &mut R) -> (i64, i64) {
    match d {
        Distribution::Parametric(ParametricDist::UniformInt { lo, hi }) => (*lo, *hi),
        other => {
            let a = other.sample_int(rng);
            let b = other.sample_int(rng);
            (a.min(b), a.max(b))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distribution_round_trips_through_toml() {
        let toml_src = r#"
            a = 10.5
            b = { dist = "normal", mean = 0.0, std = 1.0 }
            c = { dist = "uniform_int", lo = 5, hi = 10 }
            d = { dist = "beta", alpha = 2.0, beta = 5.0 }
            e = { dist = "lognormal", mu = -0.7, sigma = 0.15 }
        "#;

        #[derive(Debug, Deserialize, Serialize)]
        struct Row {
            a: Distribution,
            b: Distribution,
            c: Distribution,
            d: Distribution,
            e: Distribution,
        }

        let row: Row = toml::from_str(toml_src).expect("parse");
        assert!(matches!(row.a, Distribution::Fixed(_)));
        assert!(matches!(row.b, Distribution::Parametric(ParametricDist::Normal { .. })));
        assert!(matches!(row.c, Distribution::Parametric(ParametricDist::UniformInt { .. })));
        assert!(matches!(row.d, Distribution::Parametric(ParametricDist::Beta { .. })));
        assert!(matches!(row.e, Distribution::Parametric(ParametricDist::Lognormal { .. })));

        let serialized = toml::to_string(&row).expect("serialize");
        let reparsed: Row = toml::from_str(&serialized).expect("reparse");
        assert!(matches!(reparsed.a, Distribution::Fixed(x) if (x - 10.5).abs() < 1e-9));
    }

    #[test]
    fn unknown_distribution_kind_errors() {
        let toml_src = r#"x = { dist = "chimera", foo = 1.0 }"#;
        #[derive(Debug, Deserialize)]
        struct Row { #[allow(dead_code)] x: Distribution }
        let result: Result<Row, _> = toml::from_str(toml_src);
        assert!(result.is_err(), "expected unknown-dist error, got {:?}", result);
    }

    #[test]
    fn product_config_parses_full_toml_shape() {
        let toml_src = r#"
            [meta]
            round = 1
            ticks_per_day = 10000
            shared_position_limit = 80

            [[products]]
            name = "ASH_COATED_OSMIUM"
            position_limit = 80

            [products.fv_process]
            model = "mean_revert_ou"
            center = 10000.0
            kappa  = { dist = "normal", mean = 0.015, std = 0.004 }
            sigma  = { dist = "lognormal", mu = -0.7, sigma = 0.15 }

            [products.bot1]
            bid_rule = "round_fv_minus_offset"
            ask_rule = "round_fv_plus_offset"
            offset   = 10.0
            volume   = { dist = "uniform_int", lo = 20, hi = 30 }

            [products.bot2]
            bid_rule = "floor_fv_plus_0_75_minus_offset"
            ask_rule = "ceil_fv_plus_0_25_plus_offset"
            offset   = 8.0
            volume   = { dist = "uniform_int", lo = 8, hi = 15 }

            [products.bot3]
            presence_rate       = { dist = "beta", alpha = 8, beta = 120 }
            side_bid_prob       = 0.5
            price_delta_support = [-2, -1, 0, 1]
            crossing_volume     = { dist = "uniform_int", lo = 5, hi = 12 }
            passive_volume      = { dist = "uniform_int", lo = 2, hi = 6 }

            [products.taker]
            trade_active_prob = { dist = "beta", alpha = 395, beta = 19605 }
            second_trade_prob = { dist = "beta", alpha = 1,   beta = 390 }
            buy_prob          = { dist = "beta", alpha = 190, beta = 200 }
        "#;

        let cfg: SimConfig = toml::from_str(toml_src).expect("parse");
        assert_eq!(cfg.meta.round, 1);
        assert_eq!(cfg.products.len(), 1);
        let p = &cfg.products[0];
        assert_eq!(p.name, "ASH_COATED_OSMIUM");
        assert!(matches!(p.fv_process, FairValueModel::MeanRevertOU { .. }));
        assert_eq!(p.bot3.price_delta_support, vec![-2, -1, 0, 1]);
    }
}
