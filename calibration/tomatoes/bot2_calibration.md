# Bot 2 (INNER) Calibration — TOMATOES

## Method

Same as Bot 1. Uses true FV extracted from hold-1-unit submission (ID 43285). Bot 2 is identified as book levels with offset 4 < |offset from FV| < 7.5.

### Inputs
- `data/fv_and_book.json` — true FV + order book at each timestamp

## Analysis
`scripts/analyze_bot2.py` — presence analysis, offset distributions, brute-force formula search, volume analysis, run-length analysis.

### Key Discovery: Asymmetric Rounding

Bot 2 rounds the bid and ask at **different fractional thresholds**:

| FV fractional part | R_bid (bid+7) offset from floor(FV) | R_ask (ask-7) offset from floor(FV) |
|---|---|---|
| [0.00, 0.25) | 0 | 0 |
| [0.25, 0.75) | 1 | 0 |
| [0.75, 1.00) | 1 | 1 |

The bid rounds up at 0.25, the ask rounds up at 0.75. This creates:
- **Spread 13** when FV ∈ [N.25, N.75): both levels on the same integer center
- **Spread 14** when FV ∈ [N.75, N+0.25): levels on different centers

## Result

```python
bid = floor(FV + 0.75) - 7
ask = ceil(FV + 0.25) + 6
vol = randint(5, 10)    # same value for bid and ask on each tick
```

Equivalently: `bid = floor(FV - 0.25) - 6`, `ask = ceil(FV - 0.75) + 7`.

### Validation (scripts/validate_bot2.py)

| Metric | Score |
|---|---|
| Bid price match | 1982/1999 (99.1%) |
| Ask price match | 1971/1999 (98.6%) |
| Both match | 1954/1999 (97.7%) |
| Spread match | 1954/1999 (97.7%) |
| Volume distribution | Uniform [5,10], chi² = 2.95 (passes) |
| Bid=Ask vol same tick | 1999/1999 (100%) |

### Misses
45 total misses (2.3%): 17 bid misses, 28 ask misses. All ±1 tick at the 0.25 or 0.75 fractional boundary. Same pattern as Bot 1's boundary noise.

### Bot 2 Properties
- **Always present** (100% of timestamps) — NOT 54% as initially estimated from KELP multi-day data
- **Spread**: 13 (53.5%) or 14 (46.5%)
- **Offset from FV**: bid at -6.73 mean, ask at +6.73 mean
- **Symmetric**: bid and ask offsets are mirror images
- **Volume**: uniform random [5,10], independent of FV, identical both sides per tick
- **No memory**: quotes depend only on current FV
- **This is the best bid/ask** most of the time — Bot 2 defines the tradeable spread
