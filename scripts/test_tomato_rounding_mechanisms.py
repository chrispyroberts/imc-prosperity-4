from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from sim_analysis import enrich_prices, load_round0_dataset


TICKS_PER_DAY = 10_000


@dataclass(frozen=True)
class MechanismResult:
    base_rounding: str
    support: str
    pre_round: str
    outer_tie: str
    inner_tie: str
    ret0_5: float
    outer_half_mid_rate: float
    outer_spread15: float
    outer_spread17: float
    inner_all_65: float
    inner_int_77: float
    inner_int_76: float
    inner_int_67: float
    inner_half_65: float
    score: float


def round_bankers(x: float) -> int:
    return int(round(x))


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def round_half(x: float) -> float:
    return round(x * 2.0) / 2.0


def quantize(x: float, support: str) -> float:
    if support == "continuous":
        return x
    if support == "half":
        return round_half(x)
    if support == "quarter":
        return round(x * 4.0) / 4.0
    raise ValueError(support)


def is_half_tie(x: float) -> bool:
    return math.isclose(abs(x - math.floor(x)), 0.5, abs_tol=1e-9)


def get_round_fn(name: str) -> Callable[[float], int]:
    if name == "bankers":
        return round_bankers
    if name == "half_up":
        return round_half_up
    raise ValueError(name)


def pre_round_fair(value: float, mode: str, round_fn: Callable[[float], int]) -> float:
    if mode == "none":
        return value
    if mode == "integer":
        return float(round_fn(value))
    if mode == "half":
        return round_half(value)
    raise ValueError(mode)


def simulate_fair_paths(seed: int, support: str) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    starts = [5000.0, 5006.0]
    sigma = 0.55
    days = []
    for start in starts:
        path = np.empty(TICKS_PER_DAY)
        path[0] = quantize(start, support)
        for i in range(1, TICKS_PER_DAY):
            path[i] = quantize(path[i - 1] + sigma * rng.normal(), support)
        days.append(path)
    return days


def apply_tie_rule(
    tie_rule: str,
    bid_target: float,
    ask_target: float,
    round_fn: Callable[[float], int],
    rng: np.random.Generator,
) -> tuple[int, int]:
    if tie_rule == "base":
        return round_fn(bid_target), round_fn(ask_target)
    if tie_rule == "outward":
        return math.floor(bid_target), math.ceil(ask_target)
    if tie_rule == "inward":
        return math.ceil(bid_target), math.floor(ask_target)
    if tie_rule.startswith("mix_"):
        inward_prob = float(tie_rule.split("_", 1)[1])
        if rng.random() < inward_prob:
            return math.ceil(bid_target), math.floor(ask_target)
        return math.floor(bid_target), math.ceil(ask_target)
    raise ValueError(tie_rule)


def quote_pair(
    fair: float,
    outer: bool,
    round_fn: Callable[[float], int],
    pre_round: str,
    outer_tie: str,
    inner_tie: str,
    rng: np.random.Generator,
) -> tuple[int, int]:
    spread = 8.0 if outer else 6.5
    base_fair = pre_round_fair(fair, pre_round, round_fn)
    bid_target = base_fair - spread
    ask_target = base_fair + spread
    tie_rule = outer_tie if outer else inner_tie

    if is_half_tie(bid_target) and is_half_tie(ask_target):
        return apply_tie_rule(tie_rule, bid_target, ask_target, round_fn, rng)
    return round_fn(bid_target), round_fn(ask_target)


def summarize_model(
    seed: int,
    support: str,
    base_rounding: str,
    pre_round: str,
    outer_tie: str,
    inner_tie: str,
) -> MechanismResult:
    rng = np.random.default_rng(seed + hash((support, base_rounding, pre_round, outer_tie, inner_tie)) % (2**32))
    round_fn = get_round_fn(base_rounding)
    days = simulate_fair_paths(seed, support)

    observed_fair = []
    outer_spreads = []
    inner_combos_all = []
    inner_combos_int = []
    inner_combos_half = []

    for path in days:
        for fair in path:
            outer_bid, outer_ask = quote_pair(fair, True, round_fn, pre_round, outer_tie, inner_tie, rng)
            inner_bid, inner_ask = quote_pair(fair, False, round_fn, pre_round, outer_tie, inner_tie, rng)
            visible = (outer_bid + outer_ask) / 2.0
            observed_fair.append(visible)
            inner_combo = (inner_bid - visible, inner_ask - visible)
            inner_combos_all.append(inner_combo)
            if abs(visible % 1.0 - 0.5) < 1e-9:
                outer_spreads.append(outer_ask - outer_bid)
                inner_combos_half.append(inner_combo)
            if abs(visible % 1.0) < 1e-9:
                inner_combos_int.append(inner_combo)

    fair_series = pd.Series(observed_fair)
    abs_ret = fair_series.diff().abs().dropna()
    spread_series = pd.Series(outer_spreads)
    combo_all = pd.Series(inner_combos_all, dtype=object)
    combo_int = pd.Series(inner_combos_int, dtype=object)
    combo_half = pd.Series(inner_combos_half, dtype=object)

    ret0_5 = float((abs_ret == 0.5).mean())
    outer_half_mid_rate = float((((fair_series % 1.0) - 0.5).abs() < 1e-9).mean())
    outer15 = float((spread_series == 15).mean()) if len(spread_series) else 0.0
    outer17 = float((spread_series == 17).mean()) if len(spread_series) else 0.0
    inner_all_65 = float(combo_all.map(lambda x: x == (-6.5, 6.5)).mean()) if len(combo_all) else 0.0
    inner_int_77 = float(combo_int.map(lambda x: x == (-7.0, 7.0)).mean()) if len(combo_int) else 0.0
    inner_int_76 = float(combo_int.map(lambda x: x == (-7.0, 6.0)).mean()) if len(combo_int) else 0.0
    inner_int_67 = float(combo_int.map(lambda x: x == (-6.0, 7.0)).mean()) if len(combo_int) else 0.0
    inner_half_65 = float(combo_half.map(lambda x: x == (-6.5, 6.5)).mean()) if len(combo_half) else 0.0

    targets = {
        "ret0_5": 0.0831,
        "outer_half_mid_rate": 0.0467,
        "outer15": 0.7290,
        "outer17": 0.2710,
        "inner_all_65": 0.0467,
        "inner_int_77": 0.5062,
        "inner_int_76": 0.2517,
        "inner_int_67": 0.2421,
        "inner_half_65": 1.0,
    }
    score = (
        abs(ret0_5 - targets["ret0_5"])
        + abs(outer_half_mid_rate - targets["outer_half_mid_rate"])
        + abs(outer15 - targets["outer15"])
        + abs(outer17 - targets["outer17"])
        + abs(inner_all_65 - targets["inner_all_65"])
        + abs(inner_int_77 - targets["inner_int_77"])
        + abs(inner_int_76 - targets["inner_int_76"])
        + abs(inner_int_67 - targets["inner_int_67"])
        + abs(inner_half_65 - targets["inner_half_65"])
    )

    return MechanismResult(
        base_rounding=base_rounding,
        support=support,
        pre_round=pre_round,
        outer_tie=outer_tie,
        inner_tie=inner_tie,
        ret0_5=ret0_5,
        outer_half_mid_rate=outer_half_mid_rate,
        outer_spread15=outer15,
        outer_spread17=outer17,
        inner_all_65=inner_all_65,
        inner_int_77=inner_int_77,
        inner_int_76=inner_int_76,
        inner_int_67=inner_int_67,
        inner_half_65=inner_half_65,
        score=score,
    )


def actual_targets() -> dict[str, float]:
    prices, _ = load_round0_dataset(Path("data/round0"))
    tomatoes = enrich_prices(prices)
    tomatoes = tomatoes[tomatoes["product"] == "TOMATOES"].sort_values(["day", "timestamp"]).copy()

    base = tomatoes[(tomatoes["bid_price_3"].isna()) & (tomatoes["ask_price_3"].isna())].copy()
    abs_ret = tomatoes["fair"].diff().abs().dropna()
    int_base = base[(base["fair"] % 1.0).abs() < 1e-9].copy()
    half_base = base[(base["fair"] % 1.0 - 0.5).abs() < 1e-9].copy()
    combo_all = pd.Series(
        list(zip(base["bid_price_1"] - base["fair"], base["ask_price_1"] - base["fair"])),
        dtype=object,
    )
    combo_series = pd.Series(
        list(zip(int_base["bid_price_1"] - int_base["fair"], int_base["ask_price_1"] - int_base["fair"])),
        dtype=object,
    )
    combo_half = pd.Series(
        list(zip(half_base["bid_price_1"] - half_base["fair"], half_base["ask_price_1"] - half_base["fair"])),
        dtype=object,
    )

    return {
        "ret0_5": float((abs_ret == 0.5).mean()),
        "outer_half_mid_rate": float((((base["fair"] % 1.0) - 0.5).abs() < 1e-9).mean()),
        "outer15": float(((half_base["ask_price_2"] - half_base["bid_price_2"]) == 15).mean()),
        "outer17": float(((half_base["ask_price_2"] - half_base["bid_price_2"]) == 17).mean()),
        "inner_all_65": float(combo_all.map(lambda x: x == (-6.5, 6.5)).mean()),
        "inner_int_77": float(combo_series.map(lambda x: x == (-7.0, 7.0)).mean()),
        "inner_int_76": float(combo_series.map(lambda x: x == (-7.0, 6.0)).mean()),
        "inner_int_67": float(combo_series.map(lambda x: x == (-6.0, 7.0)).mean()),
        "inner_half_65": float(combo_half.map(lambda x: x == (-6.5, 6.5)).mean()),
    }


def main() -> None:
    print("Actual targets")
    print(actual_targets())

    rows = []
    for support in ("continuous", "half", "quarter"):
        for base_rounding in ("bankers", "half_up"):
            for pre_round in ("none", "integer", "half"):
                for outer_tie in ("base", "outward", "inward", "mix_0.25", "mix_0.5", "mix_0.75"):
                    for inner_tie in ("base", "outward", "inward"):
                        rows.append(
                            summarize_model(
                                20260401,
                                support,
                                base_rounding,
                                pre_round,
                                outer_tie,
                                inner_tie,
                            ).__dict__
                        )

    frame = pd.DataFrame(rows).sort_values("score").reset_index(drop=True)
    output_dir = Path("tmp/tomato_rounding_search")
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "results.csv", index=False)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print("\nModel comparison")
        print(frame.head(20).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
