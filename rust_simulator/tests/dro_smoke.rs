use std::process::Command;

#[test]
#[ignore]
fn dro_flag_produces_dro_report() {
    let tmp = tempfile::tempdir().unwrap();
    let output_dir = tmp.path().to_path_buf();
    let bin = env!("CARGO_BIN_EXE_rust_simulator");
    let status = Command::new(bin)
        .args([
            "--config", "../configs/tutorial.toml",
            "--strategy", "../example_trader.py",
            "--sessions", "3",
            "--seed", "42",
            "--python-bin", "../backtester/.venv/bin/python3",
            "--write-session-limit", "3",
            "--output", output_dir.to_str().unwrap(),
            "--dro", "--dro-k", "3",
        ])
        .status()
        .unwrap();
    assert!(status.success(), "binary exited non-zero");
    let dro_report = output_dir.join("dro_report.json");
    assert!(dro_report.exists(), "dro_report.json missing at {:?}", dro_report);
    let parsed: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&dro_report).unwrap()).unwrap();
    assert_eq!(parsed["k"], 3);
    assert!(parsed["sessions"].as_array().unwrap().len() == 3);
    // worst-case mean must be <= nominal mean (by construction)
    let nom = parsed["nominal_mean_pnl"].as_f64().unwrap();
    let worst = parsed["worst_case_mean_pnl"].as_f64().unwrap();
    assert!(worst <= nom + 1e-6, "worst={} > nominal={}", worst, nom);
}
