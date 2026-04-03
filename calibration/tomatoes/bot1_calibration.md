# Bot 1 (WALL) Calibration — TOMATOES

## Method

### Inputs Required
1. **True FV stream**: Extracted from a "hold 1 unit" submission. We submitted `trader_hold1.py` which buys 1 TOMATO at t=0 and holds. Server PnL at each tick = `position × server_FV - buy_cost`, so `server_FV(t) = PnL(t) + buy_price`. Submission ID: 43285.
2. **Order book at each step**: From the same submission's activities log — bid/ask prices and volumes at 3 levels.

### Extraction
`scripts/extract_fv_and_book.py` parses the submission JSON, computes FV from PnL + buy_price, and saves the full order book + FV at each timestamp to `data/fv_and_book.json`.

### Key Discovery
The server uses a **continuous fair value** for PnL calculation, quantized to 1/2048 (~0.0005). This is NOT the order book mid-price (which is half-integer). The FV is a pure random walk: N(0, 0.496²) per step, zero autocorrelation, zero kurtosis, Gaussian.

### Bot Identification
Bot 1 is the deepest (worst) level in the book — always present on both sides. Identified by `|offset from FV| > 7`.

## Analysis
`scripts/analyze_bot1.py` — brute-force tests every combination of `floor/ceil/round(FV + shift) + offset` to find the quote rule. `scripts/bot1_exact_rule.py` — examines the exact rounding behavior and transition points.

### Transfer Function: FV → Bot 1 Quotes

| FV fractional part | wall_mid offset from floor(FV) | Bot 1 bid | Bot 1 ask |
|---|---|---|---|
| [0.05, 0.45] | 0.0 | floor(FV) - 8 = round(FV) - 8 | floor(FV) + 8 = round(FV) + 8 |
| ~0.50 (±0.03) | 0.0 or 0.5 or 1.0 (noisy) | round(FV) - 8 ± 1 | round(FV) + 8 ± 1 |
| [0.55, 0.95] | 1.0 | floor(FV) + 1 - 8 = round(FV) - 8 | floor(FV) + 1 + 8 = round(FV) + 8 |

## Result

```python
bid = round(FV) - 8
ask = round(FV) + 8
vol = randint(15, 25)    # same value for bid and ask on each tick
```

### Validation (scripts/validate_bot1.py)

| Metric | Score |
|---|---|
| Bid price match | 1966/1999 (98.3%) |
| Ask price match | 1968/1999 (98.4%) |
| Both match | 1935/1999 (96.8%) |
| Spread match | 1935/1999 (96.8%) |
| Volume distribution | Uniform [15,25], chi² = 10.6 (passes uniformity test) |
| Bid=Ask vol same tick | 1999/1999 (100%) |

### Misses
All 64 misses (3.2%) occur when FV is within ±0.03 of a X.5 boundary. The miss is always ±1 tick — the rounding flips one side toward FV, narrowing the spread from 16 to 15 (62 cases) or widening to 17 (2 cases). This is likely floating-point precision in IMC's rounding implementation, not a separate behavior.

### Bot 1 Properties
- **Always present** (100% of timestamps)
- **Spread**: 15 (3.1%) or 16 (96.8%) or 17 (0.1%)
- **Offset from FV**: ±7.75 mean, ±0.45 std
- **Symmetric**: bid and ask offsets are mirror images
- **Volume**: uniform random [15,25], independent of FV, identical both sides per tick
- **No memory**: quotes depend only on current FV, not on history
