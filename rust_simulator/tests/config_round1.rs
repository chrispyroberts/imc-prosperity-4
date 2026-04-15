use rust_simulator::config::{FairValueModel, SimConfig};

#[test]
fn round1_toml_loads_and_has_expected_products() {
    let raw = std::fs::read_to_string("../configs/round1.toml").expect("read round1.toml");
    let cfg: SimConfig = toml::from_str(&raw).expect("parse round1.toml");
    assert_eq!(cfg.meta.round, 1);
    let names: Vec<_> = cfg.products.iter().map(|p| p.name.as_str()).collect();
    assert!(names.contains(&"ASH_COATED_OSMIUM"), "osmium missing: {:?}", names);
    assert!(names.contains(&"INTARIAN_PEPPER_ROOT"), "pepper missing: {:?}", names);
    for p in &cfg.products {
        assert_eq!(p.position_limit, 80);
    }
    let osmium = cfg.products.iter().find(|p| p.name == "ASH_COATED_OSMIUM").unwrap();
    assert!(matches!(osmium.fv_process, FairValueModel::MeanRevertOU { .. }));
    let pepper = cfg.products.iter().find(|p| p.name == "INTARIAN_PEPPER_ROOT").unwrap();
    assert!(matches!(pepper.fv_process, FairValueModel::DriftingWalk { .. }));
}
