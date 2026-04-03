# Bot 3 (NEAR-FV) Calibration — TOMATOES

## Method

Same as Bot 1/2. Bot 3 is identified as any book level with |offset from FV| ≤ 4, which is inside Bot 2's spread.

### Inputs
- `data/fv_and_book.json` — true FV + order book at each timestamp

## Analysis
`scripts/analyze_bot2.py` (Bot 3 section at bottom) — presence, offset distribution, volume, run lengths.

### Key Findings

**Bot 3 is a rare, single-sided, 1-tick random quote.**

| Property | Value |
|---|---|
| Presence | 125/1999 timestamps (6.3%) |
| Duration | Almost always 1 tick (92% of runs are length 1) |
| Sides | **Always single-sided**: 58 bid events, 67 ask events, 0 both |
| Price | `round(FV) + uniform_choice(-2, -1, 0, +1)` — nearly uniform (25% each) |
| Volume | **Crossing orders** (bid>FV or ask<FV): U(5,12), mean 8.1. **Passive orders** (bid<FV or ask>FV): U(2,6), mean 4.2 |
| Pattern | No correlation with FV level, fractional part, or time |

### Key Discovery: Volume Depends on Crossing

The "two clusters" in the offset distribution correspond to two different behaviors:
- **Crossing quotes** (52 events): price is on the wrong side of FV (bid above FV, or ask below FV). These are aggressive, larger orders (vol 5-12, mean 8.1).
- **Passive quotes** (73 events): price is on the normal side of FV. These are small resting orders (vol 2-6, mean 4.2).

### Interpretation

Bot 3 appears to be a **simulated market participant** (not a market maker). It places a single limit order on one side at a random integer near FV. Crossing orders are larger — consistent with an aggressive taker that leaves a resting limit when not fully filled.

For simulation purposes, Bot 3 is noise — it adds a very occasional extra level inside the spread, but it's present too rarely and for too short to meaningfully affect market making strategy.

## Result

```python
def bot3_quote(fv):
    if random.random() > 0.063:
        return None  # absent 93.7% of the time
    side = 'bid' if random.random() < 0.46 else 'ask'
    price = round(fv) + random.choice([-2, -1, 0, 1])
    # Crossing orders are larger
    if (side == 'bid' and price > fv) or (side == 'ask' and price < fv):
        vol = random.randint(5, 12)  # aggressive, mean 8.1
    else:
        vol = random.randint(2, 6)   # passive, mean 4.2
    return side, price, vol
```

### Validation (scripts/validate_bot3.py)

| Metric | Actual | Model | Match? |
|---|---|---|---|
| Presence rate | 6.3% | 6.3% | Yes |
| Side split | 46/54 | 50/50 | Yes (see stat test below) |
| Price offset | {-2: 24.8%, -1: 26.4%, 0: 28.0%, +1: 20.8%} | uniform 25% each | Yes (see stat test below) |
| Crossing rate | 41.6% | 48.9% | Marginal (p=0.10, not significant) |
| Crossing vol | mean 8.1, [5,12] | mean 8.5, U(5,12) | Yes |
| Passive vol | mean 4.2, [2,6] | mean 4.0, U(2,6) | Yes |

### Statistical Tests

**Side split (bid vs ask): is it 50/50?**

Observed: 58 bids, 67 asks out of 125 events (46.4% / 53.6%).
Under H0 of 50/50: z = 0.72, **p = 0.47**. A 47% chance of seeing this split or worse from a fair coin. Not significant — consistent with 50/50. No hardcoding needed.

**Price delta distribution: is it uniform over {-2, -1, 0, +1}?**

Observed: {-2: 31, -1: 33, 0: 35, +1: 26}. Expected: 31.25 each.
Chi-squared = 1.43, df=3, **p = 0.70**. A 70% chance of seeing this much deviation from uniform. Per-delta z-tests: delta=0 (28.0%) has z=+0.77 p=0.44; delta=+1 (20.8%) has z=-1.08 p=0.28. All well within noise.

**Crossing rate: is 41.6% compatible with model's 48.9%?**

z = -1.63, **p = 0.10**. Not significant at 5%. With 125 events we cannot distinguish the observed rate from the model's prediction. The side-delta correlation is suggestive but unproven.

### Bot 3 Properties
- **Rare**: 6.3% of timestamps
- **Ephemeral**: 1 tick duration (92%)
- **Single-sided**: never quotes both bid and ask
- **Near FV**: offset ±2, often inside Bot 2's spread
- **Low volume**: 2-7 units
- **No memory, no pattern**: appears random
- **Negligible impact on trading**: too rare to rely on for fills
