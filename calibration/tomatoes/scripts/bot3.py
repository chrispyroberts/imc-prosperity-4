"""
Bot 3 (NEAR-FV) simulator for TOMATOES.

Reverse-engineered from server + tutorial data using true FV.

Rule:
    Appears with probability 0.063 per tick (geometric inter-arrival)
    side  = 50/50 bid or ask
    2/3 passive, 1/3 aggressive
    Within passive or aggressive: 50/50 between the two offset options
    Duration: 1 tick

    Bid offsets: passive = {-2, -1}, aggressive = {0, +1}
    Ask offsets: passive = {0, +1},  aggressive = {-2, -1}

Volume:
    Passive:    U(2, 6),  mean ~4
    Aggressive: U(5, 12), mean ~8.5

Validated on tutorial data (n=1450 across 2 days):
    Passive/aggressive split: 65.9% / 34.1% (matches 2/3 : 1/3)
    Within-group splits: all 49-51% (matches 50/50)
    Per-side chi-squared rejects uniform but matches 2/3-1/3 model
"""

import random


def bot3_quote(fv: float):
    """
    Given true fair value, maybe return a single-sided quote.

    Returns:
        None if bot doesn't appear this tick (~94% of the time)
        ('bid', price, volume) or ('ask', price, volume) otherwise
    """
    if random.random() > 0.063:
        return None

    side = 'bid' if random.random() < 0.50 else 'ask'

    # 2/3 passive, 1/3 aggressive, then 50/50 within each group
    passive = random.random() < 2.0 / 3.0
    near = random.random() < 0.50

    if side == 'bid':
        if passive:
            offset = -1 if near else -2   # below FV
        else:
            offset = 0 if near else 1     # at/above FV
    else:
        if passive:
            offset = 0 if near else 1     # at/above FV
        else:
            offset = -1 if near else -2   # below FV

    price = round(fv) + offset

    if passive:
        vol = random.randint(2, 6)
    else:
        vol = random.randint(5, 12)

    return side, price, vol
