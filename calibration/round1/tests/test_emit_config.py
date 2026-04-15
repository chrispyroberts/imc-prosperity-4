import json
import tomllib
from pathlib import Path

from calibration.round1.scripts.emit_config import emit_round1_toml


def _write_stub_bots(path: Path) -> None:
    path.write_text(json.dumps({
        "bot1": {"bid_rule": "round_fv_minus_offset", "ask_rule": "round_fv_plus_offset",
                 "offset": 10.0, "volume_lo": 20, "volume_hi": 30, "presence_rate": 1.0},
        "bot2": {"bid_rule": "round_fv_minus_offset", "ask_rule": "round_fv_plus_offset",
                 "offset": 8.0, "volume_lo": 10, "volume_hi": 15, "presence_rate": 0.95},
        "bot3": {"presence_rate_beta": [8, 120], "side_bid_prob": 0.5,
                 "price_delta_support": [-1, 0, 1],
                 "crossing_volume": [5, 12], "passive_volume": [2, 6]},
        "taker": {"trade_active_beta": [395, 19605], "second_trade_beta": [1, 390],
                  "buy_prob_beta": [1, 1]},
    }))


def _write_stub_fv(path: Path, model: str) -> None:
    if model == "mean_revert_ou":
        params = {"center": 10000.0, "kappa": 0.015, "sigma": 0.5}
        posterior = {"center": [10000.0, 0.3], "kappa": [0.015, 0.004], "sigma": [0.5, 0.07]}
    elif model == "drifting_walk":
        params = {"initial": 11940.0, "drift": 0.01, "sigma": 0.7}
        posterior = {"initial": [11940.0, 2.0], "drift": [0.01, 0.0015], "sigma": [0.7, 0.09]}
    else:
        params = {"price": 10000.0, "sigma": 0.5}
        posterior = {"price": [10000.0, 0.3], "sigma": [0.5, 0.07]}
    path.write_text(json.dumps({"model": model, "params": params, "posterior": posterior,
                                "aic": 0.0, "held_out_ll": 0.0, "residual_ljung_box_p": 0.5}))


def test_emit_round1_roundtrip(tmp_path):
    osmium_bots = tmp_path / "osm_bots.json"; _write_stub_bots(osmium_bots)
    osmium_fit = tmp_path / "osm_fit.json"; _write_stub_fv(osmium_fit, "mean_revert_ou")
    pepper_bots = tmp_path / "pep_bots.json"; _write_stub_bots(pepper_bots)
    pepper_fit = tmp_path / "pep_fit.json"; _write_stub_fv(pepper_fit, "drifting_walk")
    out = tmp_path / "round1.toml"
    emit_round1_toml(osmium_fit=osmium_fit, osmium_bots=osmium_bots,
                     pepper_fit=pepper_fit, pepper_bots=pepper_bots, out=out)
    parsed = tomllib.loads(out.read_text())
    assert parsed["meta"]["round"] == 1
    assert len(parsed["products"]) == 2
    names = {p["name"] for p in parsed["products"]}
    assert names == {"ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"}
    osmium = next(p for p in parsed["products"] if p["name"] == "ASH_COATED_OSMIUM")
    assert osmium["fv_process"]["model"] == "mean_revert_ou"
    assert osmium["bot1"]["bid_rule"] == "round_fv_minus_offset"
