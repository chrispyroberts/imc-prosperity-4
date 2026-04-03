"""
Bot 2 (INNER) simulator for TOMATOES.

Rule:
    bid = floor(FV + 0.75) - 7    (rounds at 0.25 boundary)
    ask = ceil(FV + 0.25) + 6     (rounds at 0.75 boundary)
    bid_vol = ask_vol = randint(5, 10)

Equivalently:
    bid = floor(FV - 0.25) - 6
    ask = ceil(FV - 0.75) + 7

The bid rounds UP at frac=0.25, the ask rounds UP at frac=0.75.
This means for FV in [N.25, N.75), bid and ask are on the SAME
integer center → spread = 13.
For FV in [N.75, N+0.25), they're on DIFFERENT centers → spread = 14.

Accuracy on server data: 99.1% bid, 98.6% ask, 97.7% both.
Misses are ±1 at the 0.25/0.75 boundary (same pattern as Bot 1 at 0.5).

Always present (100% of timestamps).
Volume: uniform random integer [5, 10], same for bid and ask on each tick.
"""

import math
import random


def bot2_quote(fv: float) -> tuple[int, int, int]:
    """
    Given true fair value, return (bid_price, ask_price, volume).
    """
    bid = math.floor(fv + 0.75) - 7
    ask = math.ceil(fv + 0.25) + 6
    vol = random.randint(5, 10)
    return bid, ask, vol
