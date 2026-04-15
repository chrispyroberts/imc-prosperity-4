"""Validates PEPPER Bot 1 quote rule and reports quote-match metrics.

PEPPER uses asymmetric rules:
  bid = ceil(FV) - 10  (i.e., ceil_fv_minus_offset, offset=10)
  ask = floor(FV) + 10  (i.e., floor_fv_plus_offset, offset=10)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from calibration.round1.lib.stats import chi_squared_uniform, z_test_binomial
from calibration.round1.scripts.classify_levels import classify, TaggedLevel


PRODUCT = "INTARIAN_PEPPER_ROOT"
FV_AND_BOOK = Path("calibration/round1/data/fv_and_book_intarian_pepper_root.json")

OPS = {"round": round, "floor": math.floor, "ceil": math.ceil}


def _rule_to_op_shift(rule: str) -> tuple[str, float]:
  """convert rule string to (op, shift) pair."""
  if rule == "round_fv_minus_offset":
    return "round", 0.0
  if rule == "round_fv_plus_offset":
    return "round", 0.0
  if rule == "floor_fv_minus_offset":
    return "floor", 0.0
  if rule == "floor_fv_plus_offset":
    return "floor", 0.0
  if rule == "ceil_fv_minus_offset":
    return "ceil", 0.0
  if rule == "ceil_fv_plus_offset":
    return "ceil", 0.0
  if rule == "floor_fv_plus_0_75_minus_offset":
    return "floor", 0.75
  if rule == "ceil_fv_plus_0_25_plus_offset":
    return "ceil", 0.25
  raise ValueError(f"unknown rule: {rule}")


def _load_from_bots_json(product_dir: Path, bot_key: str = "bot1") -> dict:
  """load bot params from bots.json in product_dir."""
  bots_path = product_dir / "bots.json"
  bots = json.loads(bots_path.read_text())
  return bots[bot_key]


def validate(
    product: str,
    fv_and_book: Path,
    bid_rule: dict,
    ask_rule: dict,
    vol_lo: int,
    vol_hi: int,
) -> dict:
    tagged = classify(fv_and_book, product)
    bot1 = [t for t in tagged if t.bot == "bot1"]

    bid_match = ask_match = vols_in_range = 0
    paired_vol_equal = paired_vol_total = 0
    bid_vols: list[int] = []
    ask_vols: list[int] = []

    by_ts: dict[int, list[TaggedLevel]] = {}
    for t in bot1:
        by_ts.setdefault(t.timestamp, []).append(t)

    bid_op = OPS[bid_rule["op"]]
    ask_op = OPS[ask_rule["op"]]

    for ts, levels in by_ts.items():
        bids = [x for x in levels if x.side == "bid"]
        asks = [x for x in levels if x.side == "ask"]
        for b in bids:
            fv = b.price - b.offset
            expected = bid_op(fv + bid_rule["shift"]) - bid_rule["offset"]
            if expected == b.price:
                bid_match += 1
            bid_vols.append(b.quantity)
            if vol_lo <= b.quantity <= vol_hi:
                vols_in_range += 1
        for a in asks:
            fv = a.price - a.offset
            expected = ask_op(fv + ask_rule["shift"]) + ask_rule["offset"]
            if expected == a.price:
                ask_match += 1
            ask_vols.append(a.quantity)
            if vol_lo <= a.quantity <= vol_hi:
                vols_in_range += 1
        if len(bids) == 1 and len(asks) == 1:
            paired_vol_total += 1
            if bids[0].quantity == asks[0].quantity:
                paired_vol_equal += 1

    n_bid = len(bid_vols)
    n_ask = len(ask_vols)
    all_vols = bid_vols + ask_vols

    support = list(range(vol_lo, vol_hi + 1))
    vol_counts = Counter(all_vols)
    observed = np.array([vol_counts.get(v, 0) for v in support], dtype=float)
    chi_p = chi_squared_uniform(observed) if observed.sum() > 0 else 1.0

    return {
        "product": product,
        "bid_match": bid_match,
        "bid_total": n_bid,
        "bid_match_pct": 100.0 * bid_match / max(n_bid, 1),
        "ask_match": ask_match,
        "ask_total": n_ask,
        "ask_match_pct": 100.0 * ask_match / max(n_ask, 1),
        "paired_vol_equal": paired_vol_equal,
        "paired_vol_total": paired_vol_total,
        "paired_vol_equal_pct": 100.0 * paired_vol_equal / max(paired_vol_total, 1),
        "volume_uniform_chi_sq_p": chi_p,
        "volume_in_range_pct": 100.0 * vols_in_range / max(n_bid + n_ask, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bid-op", required=False)
    ap.add_argument("--bid-shift", type=float, required=False)
    ap.add_argument("--bid-offset", type=int, required=False)
    ap.add_argument("--ask-op", required=False)
    ap.add_argument("--ask-shift", type=float, required=False)
    ap.add_argument("--ask-offset", type=int, required=False)
    ap.add_argument("--vol-lo", type=int, required=False)
    ap.add_argument("--vol-hi", type=int, required=False)
    ap.add_argument("--gate", type=float, default=0.0, help="fail if both-match < this pct")
    args = ap.parse_args()

    if args.bid_op is None:
      product_dir = Path(__file__).parent.parent
      b = _load_from_bots_json(product_dir, "bot1")
      bid_op, bid_shift = _rule_to_op_shift(b["bid_rule"])
      ask_op, ask_shift = _rule_to_op_shift(b["ask_rule"])
      bid_offset = ask_offset = b["offset"]
      vol_lo = b["volume_lo"]
      vol_hi = b["volume_hi"]
    else:
      bid_op = args.bid_op
      bid_shift = args.bid_shift
      bid_offset = args.bid_offset
      ask_op = args.ask_op
      ask_shift = args.ask_shift
      ask_offset = args.ask_offset
      vol_lo = args.vol_lo
      vol_hi = args.vol_hi

    result = validate(
        PRODUCT, FV_AND_BOOK,
        {"op": bid_op, "shift": bid_shift, "offset": bid_offset},
        {"op": ask_op, "shift": ask_shift, "offset": ask_offset},
        vol_lo, vol_hi,
    )
    print(json.dumps(result, indent=2))
    both_match = min(result["bid_match_pct"], result["ask_match_pct"])
    if args.gate > 0 and both_match < args.gate * 100:
        print(f"FAIL: both-match {both_match:.1f}% < gate {args.gate * 100:.0f}%", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
