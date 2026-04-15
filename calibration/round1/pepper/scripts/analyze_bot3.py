"""Characterizes Bot 3 (rare inside-spread quote) for INTARIAN_PEPPER_ROOT.

Per tomatoes template: presence rate, duration, side split, price-delta distribution,
passive-vs-crossing volume splits. Every structural claim runs through chi-sq or z-test.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from calibration.round1.lib.stats import chi_squared_uniform, z_test_binomial
from calibration.round1.scripts.classify_levels import classify, TaggedLevel


PRODUCT = "INTARIAN_PEPPER_ROOT"
FV_AND_BOOK = Path("calibration/round1/data/fv_and_book_intarian_pepper_root.json")


def analyze(product: str = PRODUCT, fv_and_book: Path = FV_AND_BOOK) -> dict:
    tagged = classify(fv_and_book, product)
    total_timestamps = len({t.timestamp for t in tagged})
    bot3 = [t for t in tagged if t.bot == "bot3"]
    bot3_timestamps = {t.timestamp for t in bot3}
    presence_rate = len(bot3_timestamps) / max(total_timestamps, 1)

    sides = [t.side for t in bot3]
    bid_count = sides.count("bid")
    ask_count = sides.count("ask")
    side_p = z_test_binomial(bid_count, len(sides), 0.5) if sides else 1.0

    # single-sided per timestamp
    both_sided = 0
    single_sided = 0
    by_ts: dict[int, list[str]] = defaultdict(list)
    for t in bot3:
        by_ts[t.timestamp].append(t.side)
    for sides_at_ts in by_ts.values():
        if "bid" in sides_at_ts and "ask" in sides_at_ts:
            both_sided += 1
        else:
            single_sided += 1

    # price delta: round(price) - round(fv)
    deltas = [round(t.price) - round(t.price - t.offset) for t in bot3]
    delta_counts = Counter(deltas)
    delta_support = sorted(delta_counts)
    delta_observed = [delta_counts[d] for d in delta_support]
    delta_p = chi_squared_uniform(np.array(delta_observed)) if delta_observed else 1.0

    # crossing: bid > fv or ask < fv (aggressive); else passive
    crossing = []
    passive = []
    for t in bot3:
        fv = t.price - t.offset
        is_crossing = (t.side == "bid" and t.price > fv) or (t.side == "ask" and t.price < fv)
        (crossing if is_crossing else passive).append(t.quantity)

    crossing_vol_range = (min(crossing), max(crossing)) if crossing else (0, 0)
    passive_vol_range = (min(passive), max(passive)) if passive else (0, 0)

    return {
        "product": product,
        "presence_rate": presence_rate,
        "n_bot3": len(bot3),
        "n_bot3_timestamps": len(bot3_timestamps),
        "total_timestamps": total_timestamps,
        "side_bid_count": bid_count,
        "side_ask_count": ask_count,
        "side_50_50_p": side_p,
        "both_sided_timestamps": both_sided,
        "single_sided_timestamps": single_sided,
        "delta_support": delta_support,
        "delta_counts": dict(delta_counts),
        "delta_uniform_p": delta_p,
        "crossing_n": len(crossing),
        "passive_n": len(passive),
        "crossing_vol_range": crossing_vol_range,
        "crossing_vol_mean": float(np.mean(crossing)) if crossing else 0.0,
        "passive_vol_range": passive_vol_range,
        "passive_vol_mean": float(np.mean(passive)) if passive else 0.0,
    }


def main() -> None:
    print(json.dumps(analyze(), indent=2))


if __name__ == "__main__":
    main()
