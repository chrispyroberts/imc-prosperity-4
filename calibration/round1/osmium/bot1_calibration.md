# Bot 1 (WALL) Calibration -- ASH_COATED_OSMIUM

## Method

Same pattern as TOMATOES Bot 1 calibration (`calibration/tomatoes/bot1_calibration.md`).
Source: hold-1 submission (day 0 website test run, 1000 ticks).

Bot 1 levels identified as `|offset from FV| >= 9.0`, using thresholds in
`calibration/round1/scripts/classify_levels.py`.

Brute-force search over `{floor, ceil, round}(FV + shift) +/- offset` for all
shifts in {-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1} and offsets in [5, 19].

## Result

```python
bid = floor(FV) - 10      # equivalent: round(FV + 0.5) - 11
ask = ceil(FV) + 10       # equivalent: round(FV - 0.5) + 11
vol = randint(20, 30)     # same value for bid and ask on each tick
```

Rust rule strings (used by `products.rs::quote_price_for_rule`):
- bid: `floor_fv_minus_offset`, offset=10
- ask: `ceil_fv_plus_offset`, offset=10

### Structural note

The floor/ceil pairing widens the spread for fractional FV:
for FV = X.Y (Y > 0), spread = (X+1+10) - (X-10) = 21.
For integer FV, spread = 20.
This is why the outer levels sit ~10.5 away from FV on average.

## Validation

| Metric | Score |
|---|---|
| Bid price match | 791/794 (99.6%) |
| Ask price match | 778/778 (100.0%) |
| Both match (min) | 99.6% |
| Bid=Ask volume same tick | 628/628 (100.0%) |
| Volume in range [20, 30] | 100.0% |
| Volume uniform chi-sq p | 0.095 (passes, p > 0.05) |

## Statistical Tests

- Volume uniformity chi-squared: p = 0.095 -- cannot reject uniform [20, 30].
- Bid/ask offset symmetry: both sides use offset=10; the rounding ops (floor/ceil)
  are different but the nominal integer offset is the same. Symmetric in offset.
- 3 bid misses (0.4%): two occur at FV near X.999 boundary where brute-force identifies
  the same miss pattern as TOMATOES (rounding ambiguity at half-integer FV). One miss
  at ts=0 where the book had an anomalous opening spread.

## Bot 1 Properties

- Presence: approx 80% of timestamps (bot not always in book on both sides,
  especially early ticks and ticks where only one side is quoted)
- Spread: 20 (integer FV) or 21 (fractional FV, ~99% of ticks)
- Offset from FV: ~10.5 mean (floor rounds down on bid, ceil rounds up on ask)
- Symmetric: yes (same integer offset=10 both sides)
- Volume: uniform random [20, 30], independent of FV, identical both sides per tick
- No memory: quotes depend only on current FV
