from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from sim_analysis import enrich_prices, load_round0_dataset


@dataclass(frozen=True)
class GResult:
    family: str
    exact_state_match: float
    outer_half_mid_rate: float
    outer_spread15: float
    outer_spread17: float
    inner_all_77: float
    inner_all_76: float
    inner_all_67: float
    inner_all_65: float
    inner_int_77: float
    inner_int_76: float
    inner_int_67: float
    inner_half_65: float
    score: float


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def frac01(x: float) -> float:
    return x - math.floor(x)


def identity(x: float) -> float:
    return x


def nearest_half(x: float) -> float:
    return round(x * 2.0) / 2.0


def nearest_quarter(x: float) -> float:
    return round(x * 4.0) / 4.0


def floor_quarter(x: float) -> float:
    return math.floor(x * 4.0) / 4.0


def ceil_quarter(x: float) -> float:
    return math.ceil(x * 4.0) / 4.0


def skew_quarter_down(x: float) -> float:
    base = math.floor(x)
    frac = frac01(x)
    if frac < 0.125:
        return base + 0.0
    if frac < 0.625:
        return base + 0.25
    if frac < 0.875:
        return base + 0.75
    return base + 1.0


def skew_quarter_up(x: float) -> float:
    base = math.floor(x)
    frac = frac01(x)
    if frac < 0.125:
        return base + 0.0
    if frac < 0.375:
        return base + 0.25
    if frac < 0.875:
        return base + 0.75
    return base + 1.0


G_FAMILIES: dict[str, Callable[[float], float]] = {
    "identity": identity,
    "nearest_half": nearest_half,
    "nearest_quarter": nearest_quarter,
    "floor_quarter": floor_quarter,
    "ceil_quarter": ceil_quarter,
    "skew_quarter_down": skew_quarter_down,
    "skew_quarter_up": skew_quarter_up,
}


def make_base_frame() -> pd.DataFrame:
    prices, _ = load_round0_dataset(Path("data/round0"))
    enriched = enrich_prices(prices)
    tomatoes = enriched[enriched["product"] == "TOMATOES"].sort_values(["day", "timestamp"]).copy()
    base = tomatoes[(tomatoes["bid_price_3"].isna()) & (tomatoes["ask_price_3"].isna())].copy()
    base["actual_outer_mid"] = (base["bid_price_2"] + base["ask_price_2"]) / 2.0
    base["actual_outer_spread"] = base["ask_price_2"] - base["bid_price_2"]
    base["actual_inner_combo"] = list(
        zip(base["bid_price_1"] - base["actual_outer_mid"], base["ask_price_1"] - base["actual_outer_mid"])
    )
    return base.reset_index(drop=True)


def summarize_predicted(base: pd.DataFrame, family: str) -> GResult:
    g = G_FAMILIES[family]
    frame = base.copy()
    frame["center"] = frame["latent_fair"].map(g)
    frame["pred_outer_bid"] = (frame["center"] - 8.0).map(round_half_up)
    frame["pred_outer_ask"] = (frame["center"] + 8.0).map(round_half_up)
    frame["pred_inner_bid"] = (frame["center"] - 6.5).map(round_half_up)
    frame["pred_inner_ask"] = (frame["center"] + 6.5).map(round_half_up)
    frame["pred_outer_mid"] = (frame["pred_outer_bid"] + frame["pred_outer_ask"]) / 2.0
    frame["pred_outer_spread"] = frame["pred_outer_ask"] - frame["pred_outer_bid"]
    frame["pred_inner_combo"] = list(
        zip(frame["pred_inner_bid"] - frame["pred_outer_mid"], frame["pred_inner_ask"] - frame["pred_outer_mid"])
    )
    frame["exact_match"] = (
        (frame["pred_outer_spread"] == frame["actual_outer_spread"])
        & (frame["pred_inner_combo"] == frame["actual_inner_combo"])
    )

    pred_half = frame[(frame["pred_outer_mid"] % 1.0 - 0.5).abs() < 1e-9].copy()
    pred_int = frame[(frame["pred_outer_mid"] % 1.0).abs() < 1e-9].copy()

    def combo_rate(sub: pd.DataFrame, combo: tuple[float, float]) -> float:
        if len(sub) == 0:
            return 0.0
        return float((sub["pred_inner_combo"] == combo).mean())

    metrics = {
        "outer_half_mid_rate": float((((frame["pred_outer_mid"] % 1.0) - 0.5).abs() < 1e-9).mean()),
        "outer_spread15": float((pred_half["pred_outer_spread"] == 15).mean()) if len(pred_half) else 0.0,
        "outer_spread17": float((pred_half["pred_outer_spread"] == 17).mean()) if len(pred_half) else 0.0,
        "inner_all_77": combo_rate(frame, (-7.0, 7.0)),
        "inner_all_76": combo_rate(frame, (-7.0, 6.0)),
        "inner_all_67": combo_rate(frame, (-6.0, 7.0)),
        "inner_all_65": combo_rate(frame, (-6.5, 6.5)),
        "inner_int_77": combo_rate(pred_int, (-7.0, 7.0)),
        "inner_int_76": combo_rate(pred_int, (-7.0, 6.0)),
        "inner_int_67": combo_rate(pred_int, (-6.0, 7.0)),
        "inner_half_65": combo_rate(pred_half, (-6.5, 6.5)),
    }

    targets = {
        "outer_half_mid_rate": 0.04672091394083095,
        "outer_spread15": 0.7289504036908881,
        "outer_spread17": 0.2710495963091119,
        "inner_all_77": 0.4825133372851215,
        "inner_all_76": 0.23996335614592876,
        "inner_all_67": 0.23080239262811877,
        "inner_all_65": 0.04672091394083095,
        "inner_int_77": 0.5061616732617298,
        "inner_int_76": 0.2517241379310345,
        "inner_int_67": 0.24211418880723573,
        "inner_half_65": 1.0,
    }
    score = sum(abs(metrics[key] - targets[key]) for key in targets)

    return GResult(
        family=family,
        exact_state_match=float(frame["exact_match"].mean()),
        score=score,
        **metrics,
    )


def main() -> None:
    base = make_base_frame()
    rows = [summarize_predicted(base, family).__dict__ for family in G_FAMILIES]
    frame = pd.DataFrame(rows).sort_values(["score", "exact_state_match"], ascending=[True, False]).reset_index(
        drop=True
    )

    output_dir = Path("tmp/tomato_g_families")
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "results.csv", index=False)

    with pd.option_context("display.max_columns", None, "display.width", 220):
        print(frame.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
