"""Validates Bot 3 calibration for ASH_COATED_OSMIUM by reprinting metrics table."""
from __future__ import annotations

import json
from pathlib import Path

from calibration.round1.osmium.scripts.analyze_bot3 import analyze, PRODUCT, FV_AND_BOOK


def main() -> None:
    result = analyze(PRODUCT, FV_AND_BOOK)
    print(json.dumps(result, indent=2))
    print()
    print("=== Bot 3 Metrics Table ===")
    print(f"Product             : {result['product']}")
    print(f"Presence rate       : {result['presence_rate']:.4f}  ({result['n_bot3_timestamps']}/{result['total_timestamps']} timestamps)")
    print(f"N events            : {result['n_bot3']}")
    print(f"Side split (bid/ask): {result['side_bid_count']}/{result['side_ask_count']}  (50/50 p={result['side_50_50_p']:.3f})")
    print(f"Both-sided ts       : {result['both_sided_timestamps']}  (single={result['single_sided_timestamps']})")
    print(f"Delta support       : {result['delta_support']}")
    print(f"Delta counts        : {result['delta_counts']}")
    print(f"Delta uniform p     : {result['delta_uniform_p']:.3f}")
    print(f"Crossing n          : {result['crossing_n']}  vol range={result['crossing_vol_range']}  mean={result['crossing_vol_mean']:.2f}")
    print(f"Passive n           : {result['passive_n']}  vol range={result['passive_vol_range']}  mean={result['passive_vol_mean']:.2f}")
    print()
    if result["n_bot3"] < 30:
        print("WARNING: fewer than 30 bot3 events; statistics are unreliable.")
    else:
        print(f"Sample size OK: {result['n_bot3']} events.")


if __name__ == "__main__":
    main()
