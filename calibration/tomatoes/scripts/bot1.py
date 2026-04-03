"""
Bot 1 (WALL) simulator for TOMATOES.

Reverse-engineered from server data using true FV extracted from PnL.

Rule:
    bid = round(FV) - 8
    ask = round(FV) + 8
    bid_vol = ask_vol = randint(15, 25)

Where round() uses standard rounding (0.5 rounds to nearest even, but
in practice FV is continuous so exact 0.5 almost never occurs).

At FV exactly near X.0: the bid/ask can be either N-8 or N+1-8
(transition zone, ~50/50 at frac=0.0).

At FV near X.5: bid rounds down (R=N), ask also rounds down (R=N),
but ~25% of the time bid rounds UP and ask rounds DOWN, giving spread=16
instead of 15. This is the "miss" pattern.

Accuracy on server data: 98.3% bid, 98.4% ask.
The ~1.7% misses are ALL ±1 from round(FV), occurring when FV is near
X.5 (the rounding boundary). The misses are symmetric: bid goes +1
(higher than expected) 32 times, ask goes -1 (lower than expected) 30
times — both moves NARROW the spread from 16 to 15, suggesting the bot
independently rounds bid and ask with slight noise near the boundary.

Volume: uniform random integer [15, 25], same for bid and ask on each tick.
"""

import math
import random


def bot1_quote(fv: float) -> tuple[int, int, int]:
    """
    Given true fair value, return (bid_price, ask_price, volume).

    Returns:
        bid: integer bid price
        ask: integer ask price
        vol: volume (same for both sides)
    """
    bid = round(fv) - 8
    ask = round(fv) + 8
    vol = random.randint(15, 25)
    return bid, ask, vol


def bot1_quote_with_noise(fv: float) -> tuple[int, int, int]:
    """
    Version with the ~1.7% boundary noise that matches server data more precisely.
    When FV is within 0.02 of a X.5 boundary, independently jitter bid/ask by ±1.
    """
    r = round(fv)
    frac = abs(fv - r)  # distance to nearest integer

    # Near the 0.5 boundary (frac close to 0.5 from the rounded integer)
    # there's ~25% chance of an extra ±1 shift
    bid = r - 8
    ask = r + 8

    dist_to_half = abs((fv % 1) - 0.5)
    if dist_to_half < 0.02:
        # In the transition zone — small chance of ±1
        if random.random() < 0.25:
            bid += 1  # narrows spread
        if random.random() < 0.25:
            ask -= 1  # narrows spread

    vol = random.randint(15, 25)
    return bid, ask, vol
