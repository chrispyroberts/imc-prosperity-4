"""Discovers Bot 2's quote rule and volume distribution for PEPPER.

Tests BOTH symmetric (round-based) and asymmetric rounding rules (tomatoes-style
floor(FV+0.75) / ceil(FV+0.25)) to decide which fits better.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from calibration.round1.scripts.classify_levels import classify, TaggedLevel


PRODUCT = "INTARIAN_PEPPER_ROOT"
FV_AND_BOOK = Path("calibration/round1/data/fv_and_book_intarian_pepper_root.json")


def bot2_levels(tagged: list[TaggedLevel]) -> list[TaggedLevel]:
    return [t for t in tagged if t.bot == "bot2"]


def brute_force_rule(bot2_side: list[TaggedLevel], side: str) -> dict:
    """Tests all (op, shift, offset) combos, for integer offsets 3..11 and common shifts."""
    best: dict = {"op": None, "shift": None, "offset": None, "match_pct": 0.0}
    n = len(bot2_side)
    if n == 0:
        return best
    for op_name, op in (("round", round), ("floor", math.floor), ("ceil", math.ceil)):
        for shift in [0.0, 0.25, 0.5, 0.75, -0.25, -0.5, -0.75]:
            for offset in range(3, 12):
                matches = 0
                for t in bot2_side:
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


def volume_distribution(bot2: list[TaggedLevel]) -> dict:
    vols = [t.quantity for t in bot2]
    if not vols:
        return {"lo": 0, "hi": 0, "mean": 0.0, "counts": {}}
    c = Counter(vols)
    return {
        "lo": min(vols),
        "hi": max(vols),
        "mean": sum(vols) / len(vols),
        "counts": {str(k): v for k, v in sorted(c.items())},
    }


def presence_rate(tagged: list[TaggedLevel], fv_and_book: Path) -> dict:
    """Count timestamps with any bot2 level vs total timestamps."""
    import json as _json
    raw = _json.loads(fv_and_book.read_text())
    total_ts = len({snap["timestamp"] for snap in raw["book"]})
    bot2_ts = {t.timestamp for t in tagged if t.bot == "bot2"}
    return {"n_bot2_ts": len(bot2_ts), "n_total_ts": total_ts,
            "presence_rate": len(bot2_ts) / total_ts if total_ts > 0 else 0.0}


def analyze(product: str, fv_and_book: Path) -> dict:
    tagged = classify(fv_and_book, product)
    bot2 = bot2_levels(tagged)
    bids = [t for t in bot2 if t.side == "bid"]
    asks = [t for t in bot2 if t.side == "ask"]
    return {
        "product": product,
        "n_bot2_levels": len(bot2),
        "n_bid": len(bids),
        "n_ask": len(asks),
        "bid_rule": brute_force_rule(bids, "bid"),
        "ask_rule": brute_force_rule(asks, "ask"),
        "bid_volume": volume_distribution(bids),
        "ask_volume": volume_distribution(asks),
        "presence": presence_rate(tagged, fv_and_book),
    }


def main() -> None:
    print(json.dumps(analyze(PRODUCT, FV_AND_BOOK), indent=2))


if __name__ == "__main__":
    main()
