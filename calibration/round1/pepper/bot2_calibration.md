# Bot 2 (INNER) Calibration -- INTARIAN_PEPPER_ROOT

## Method

Same pattern as Bot 1 calibration (`calibration/round1/pepper/bot1_calibration.md`).
Bot 2 levels identified as `5.0 <= |offset from FV| < 8.5`, using thresholds in
`calibration/round1/scripts/classify_levels.py`.

Brute-force search over `{floor, ceil, round}(FV + shift) +/- offset` for all
shifts in {-0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75} and offsets in [3, 11].
Tests both symmetric and asymmetric (tomatoes-style) rules.

### Inputs
- `calibration/round1/data/fv_and_book_intarian_pepper_root.json`

## Result

```python
bid = ceil(FV) - 7
ask = floor(FV) + 7
vol = randint(8, 12)    # same value for bid and ask on each tick
```

Rust rule strings (used by `products.rs::quote_price_for_rule`):
- bid: `ceil_fv_minus_offset`, offset=7
- ask: `floor_fv_plus_offset`, offset=7

### Comparison: Round 1 Bot 2 vs Tomatoes Bot 2

| Property | PEPPER Bot 2 | Tomatoes Bot 2 |
|---|---|---|
| Bid rule | `ceil(FV) - 7` | `floor(FV + 0.75) - 7` |
| Ask rule | `floor(FV) + 7` | `ceil(FV + 0.25) + 6` |
| Rounding type | Asymmetric (ceil bid, floor ask) | Asymmetric (different shifts) |
| Spread | 13 (frac FV) or 14 (integer FV) | 13 or 14 (depends on FV fraction) |
| Offset | 7 nominal both sides | ~6.75 bid / ~6.25 ask effective |
| Volume range | [8, 12] | [5, 10] |

PEPPER Bot 2 uses ceil/floor (same direction pairing as PEPPER Bot 1) vs tomatoes'
floor(FV+0.75)/ceil(FV+0.25) asymmetric shift pattern. Both produce variable spreads
of 13 or 14 depending on fractional FV, but via different mechanisms:
- PEPPER: ceil(FV) - floor(FV) = 0 for integer FV (spread 14) or 1 for fractional (spread 13)
- Tomatoes: the 0.75/0.25 shifts create the same 13/14 variation but using floor/ceil

### Structural note: PEPPER Bot 2 mirrors Bot 1 rounding direction

PEPPER Bot 1 uses ceil/floor (bid=ceil, ask=floor), narrowing the spread for fractional FV.
PEPPER Bot 2 uses the same direction (ceil bid, floor ask) with offset=7.
This is consistent: PEPPER's bot convention is ceil on bid, floor on ask.
OSMIUM uses the opposite convention (floor bid, ceil ask for Bot 1; round for Bot 2).

## Validation

| Metric | Score |
|---|---|
| Bid price match | 807/807 (100.0%) |
| Ask price match | 772/773 (99.9%) |
| Both match | 99.9% |
| Bid=Ask volume same tick | 619/619 (100.0%) |
| Volume in range [8, 12] | 100.0% |
| Volume uniform chi-sq p | 0.026 (marginal -- mild non-uniformity) |
| Presence rate | 961/1000 (96.1%) |

## Statistical Tests

- Volume uniformity chi-squared: p = 0.026 -- rejects strict uniform [8, 12] at alpha=0.05.
  Inspection shows slight hump at vol=10 (178 bid + 178 ask vs ~190 expected from uniform).
  The [8, 12] range is correct; distribution is approximately uniform with mild center bias.
  For simulation, uniform [8, 12] is an adequate model.
- Bid/ask offset: ceil/floor produces spread 13 for fractional FV, 14 for integer FV.
  Bid magnitude = ceil(FV) - FV + 7 = (1 - frac(FV)) + 7; ask magnitude = frac(FV) + 7.
  These are mirror images summing to 14 (or 14 for integer FV as well).
- 1 ask miss (0.1%): single tick where the observed ask deviated from floor(FV)+7 by 1.
  Consistent with boundary rounding noise at fractional FV. Not structural.

## Bot 2 Properties

- Presence: 96.1% of timestamps (structural finding: NOT always present, unlike tomatoes Bot 2)
- Spread: 13 (fractional FV) or 14 (integer FV)
- Offset from FV: 7 nominal; effective mean ~7.5 (ceil/floor add ~0.5 on average for fractional FV)
- Symmetric: same integer offset (7) both sides; ops differ (ceil bid, floor ask)
- Volume: approximately uniform [8, 12], independent of FV, identical both sides per tick
- No memory: quotes depend only on current FV

### Structural Finding: Partial Presence

Tomatoes Bot 2 was always present (100%). PEPPER Bot 2 is present 96.1% of timestamps
(961/1000). For simulation, presence_rate=0.961 should be modeled (Bernoulli draw per tick).
