"""Discovers Bot 1's quote rule and volume distribution for INTARIAN_PEPPER_ROOT.

Brute-forces every combination of floor/ceil/round(fv + shift) +/- offset
and reports the top matches for bid and ask separately.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from calibration.round1.scripts.classify_levels import classify, TaggedLevel


PRODUCT = "INTARIAN_PEPPER_ROOT"
FV_AND_BOOK = Path("calibration/round1/data/fv_and_book_intarian_pepper_root.json")


def bot1_levels(tagged: list[TaggedLevel]) -> list[TaggedLevel]:
    return [t for t in tagged if t.bot == "bot1"]


def brute_force_rule(levels: list[TaggedLevel], side: str) -> dict:
    """Find best (op, shift, offset) for the given side."""
    best: dict = {"op": None, "shift": None, "offset": None, "match_pct": 0.0}
    n = len(levels)
    if n == 0:
        return best
    for op_name, op in (("round", round), ("floor", math.floor), ("ceil", math.ceil)):
        for shift in (x * 0.25 for x in range(-4, 5)):
            for offset in range(5, 20):
                matches = 0
                for t in levels:
                    fv = t.price - t.offset
                    expected = op(fv + shift) + (-offset if side == "bid" else offset)
                    if expected == t.price:
                        matches += 1
                pct = 100.0 * matches / n
                if pct > best["match_pct"]:
                    best = {
                        "op": op_name, "shift": shift, "offset": offset,
                        "match_pct": pct, "matches": matches, "total": n,
                    }
    return best


def volume_distribution(levels: list[TaggedLevel]) -> dict:
    vols = [t.quantity for t in levels]
    if not vols:
        return {"lo": 0, "hi": 0, "mean": 0.0, "counts": {}}
    c = Counter(vols)
    return {
        "lo": min(vols),
        "hi": max(vols),
        "mean": sum(vols) / len(vols),
        "counts": {str(k): v for k, v in sorted(c.items())},
    }


def analyze(product: str = PRODUCT, fv_and_book: Path = FV_AND_BOOK) -> dict:
    tagged = classify(fv_and_book, product)
    bot1 = bot1_levels(tagged)
    bid_levels = [t for t in bot1 if t.side == "bid"]
    ask_levels = [t for t in bot1 if t.side == "ask"]
    bid_rule = brute_force_rule(bid_levels, "bid")
    ask_rule = brute_force_rule(ask_levels, "ask")
    return {
        "product": product,
        "n_bot1_levels": len(bot1),
        "n_bid": len(bid_levels),
        "n_ask": len(ask_levels),
        "bid_rule": bid_rule,
        "ask_rule": ask_rule,
        "bid_volume": volume_distribution(bid_levels),
        "ask_volume": volume_distribution(ask_levels),
    }


def main() -> None:
    result = analyze()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
