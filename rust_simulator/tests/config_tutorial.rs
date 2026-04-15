// integration: ensures tutorial.toml loads cleanly and has the two legacy products
// with the exact hardcoded constants from the pre-refactor main.rs.
use rust_simulator::config::{FairValueModel, SimConfig};

const TUTORIAL_PATH: &str = "../configs/tutorial.toml";

#[test]
fn tutorial_toml_loads_and_matches_legacy_constants() {
    let raw = std::fs::read_to_string(TUTORIAL_PATH).expect("read tutorial.toml");
    let cfg: SimConfig = toml::from_str(&raw).expect("parse tutorial.toml");
    assert_eq!(cfg.meta.round, 0);
    assert_eq!(cfg.meta.ticks_per_day, 10_000);
    assert_eq!(cfg.meta.shared_position_limit, 80);
    assert_eq!(cfg.products.len(), 2);

    let emeralds = cfg.products.iter().find(|p| p.name == "EMERALDS").expect("EMERALDS present");
    assert!(matches!(emeralds.fv_process, FairValueModel::Fixed { .. }));

    let tomatoes = cfg.products.iter().find(|p| p.name == "TOMATOES").expect("TOMATOES present");
    assert!(matches!(tomatoes.fv_process, FairValueModel::DriftingWalk { .. }));
}
