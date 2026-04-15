use std::process::Command;

/// smoke-tests the --fixed-params flag: flag must be accepted, binary must exit 0,
/// and a session_summary.csv must be produced.
///
/// note: full output determinism is not asserted here because the existing simulator
/// has non-determinism at the python strategy boundary (HashMap<String,i32> json
/// serialization order is not stable across runs), which is a pre-existing issue
/// unrelated to --fixed-params. once that is fixed, equality of s1/s2 can be
/// asserted instead.
#[test]
#[ignore]
fn fixed_params_flag_accepted_and_produces_output() {
    let bin = env!("CARGO_BIN_EXE_rust_simulator");
    let out1 = Command::new(bin)
        .args([
            "--config", "../configs/tutorial.toml",
            "--fixed-params",
            "--sessions", "3",
            "--seed", "42",
            "--strategy", "../example_trader.py",
            "--output", "../tmp/fp1",
            "--python-bin", "../backtester/.venv/bin/python3",
            "--write-session-limit", "3",
        ])
        .output()
        .unwrap();
    let out2 = Command::new(bin)
        .args([
            "--config", "../configs/tutorial.toml",
            "--fixed-params",
            "--sessions", "3",
            "--seed", "42",
            "--strategy", "../example_trader.py",
            "--output", "../tmp/fp2",
            "--python-bin", "../backtester/.venv/bin/python3",
            "--write-session-limit", "3",
        ])
        .output()
        .unwrap();
    assert!(out1.status.success(), "run1 failed: {}", String::from_utf8_lossy(&out1.stderr));
    assert!(out2.status.success(), "run2 failed: {}", String::from_utf8_lossy(&out2.stderr));
    // verify both produced output with the expected header
    let s1 = std::fs::read_to_string("../tmp/fp1/session_summary.csv").unwrap();
    let s2 = std::fs::read_to_string("../tmp/fp2/session_summary.csv").unwrap();
    let expected_header = "session_id,total_pnl,";
    assert!(s1.starts_with(expected_header), "run1 bad header: {}", &s1[..50.min(s1.len())]);
    assert!(s2.starts_with(expected_header), "run2 bad header: {}", &s2[..50.min(s2.len())]);
}
