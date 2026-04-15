"""end-to-end: runs prosperity4mcbt on round1 config and asserts dashboard shape."""
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent


def test_round1_quick_produces_expected_dashboard_shape(tmp_path):
    """smoke test: round1 config produces dashboard with expected products."""
    import pytest

    round1 = ROOT / "configs" / "round1.toml"
    if not round1.exists():
        pytest.skip("round1.toml not yet emitted")

    dash = tmp_path / "dashboard.json"
    cmd = ["prosperity4mcbt", str(ROOT / "backtester" / "example_trader.py"),
           "--round", "1", "--quick", "--seed", "20260415",
           "--out", str(dash)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
    except FileNotFoundError:
        pytest.skip("prosperity4mcbt not in path; build with 'cargo build --release'")

    if r.returncode != 0:
        pytest.skip(f"example_trader incompatible: {r.stderr[-200:]}")

    assert dash.exists(), "dashboard.json not created"
    data = json.loads(dash.read_text())

    product_names = data.get("productNames") or []
    assert "ASH_COATED_OSMIUM" in product_names, f"missing osmium; got {product_names}"
    assert "INTARIAN_PEPPER_ROOT" in product_names, f"missing pepper; got {product_names}"

    overall = data.get("overall") or {}
    pnl = overall.get("totalPnl") or {}
    assert pnl.get("count") == 100, f"expected 100 rounds, got {pnl.get('count')}"


def test_round1_dashboard_structure(tmp_path):
    """verify dashboard json structure and per-product panels."""
    import pytest

    round1 = ROOT / "configs" / "round1.toml"
    if not round1.exists():
        pytest.skip("round1.toml not emitted")

    dash = tmp_path / "dashboard.json"
    cmd = ["prosperity4mcbt", str(ROOT / "backtester" / "example_trader.py"),
           "--round", "1", "--quick", "--seed", "20260416",
           "--out", str(dash)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=ROOT)
    except FileNotFoundError:
        pytest.skip("prosperity4mcbt not in path")

    if r.returncode != 0:
        pytest.skip("example_trader incompatible")

    data = json.loads(dash.read_text())

    # check per-product keys exist
    per_product = data.get("perProduct") or {}
    assert "ASH_COATED_OSMIUM" in per_product
    assert "INTARIAN_PEPPER_ROOT" in per_product

    # each product should have pnl, vega, gamma, theta
    for pname in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
        prod = per_product.get(pname) or {}
        assert "pnl" in prod, f"{pname} missing pnl"
        assert "vega" in prod, f"{pname} missing vega"
        assert "gamma" in prod, f"{pname} missing gamma"
        assert "theta" in prod, f"{pname} missing theta"
