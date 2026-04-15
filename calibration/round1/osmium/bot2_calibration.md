# Bot 2 (INNER) Calibration -- ASH_COATED_OSMIUM

## Method

Same pattern as Bot 1 calibration (`calibration/round1/osmium/bot1_calibration.md`).
Bot 2 levels identified as `5.0 <= |offset from FV| < 9.0`, using thresholds in
`calibration/round1/scripts/classify_levels.py`.

Brute-force search over `{floor, ceil, round}(FV + shift) +/- offset` for all
shifts in {-0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75} and offsets in [3, 11].
Tests both the symmetric round-based approach and the asymmetric tomatoes-style
`floor(FV+0.75)` / `ceil(FV+0.25)` rules.

### Inputs
- `calibration/round1/data/fv_and_book_ash_coated_osmium.json`

## Result

```python
bid = round(FV) - 8
ask = round(FV) + 8
vol = randint(10, 15)    # same value for bid and ask on each tick
```

Rust rule strings (used by `products.rs::quote_price_for_rule`):
- bid: `round_fv_minus_offset`, offset=8
- ask: `round_fv_plus_offset`, offset=8

### Comparison: Round 1 Bot 2 vs Tomatoes Bot 2

| Property | OSMIUM Bot 2 | Tomatoes Bot 2 |
|---|---|---|
| Bid rule | `round(FV) - 8` | `floor(FV + 0.75) - 7` |
| Ask rule | `round(FV) + 8` | `ceil(FV + 0.25) + 6` |
| Rounding type | Symmetric (same op both sides) | Asymmetric (different thresholds) |
| Spread | Always 16 | 13 or 14 (depends on FV fraction) |
| Offset | 8 nominal | ~6.75 bid / ~6.25 ask effective |
| Volume range | [10, 15] | [5, 10] |

OSMIUM Bot 2 uses a simpler symmetric rule (round on both sides) vs the asymmetric
tomatoes floor(FV+0.75)/ceil(FV+0.25) pattern. This produces a fixed spread of 16
regardless of the fractional part of FV, compared to tomatoes' variable spread of 13/14.

## Validation

| Metric | Score |
|---|---|
| Bid price match | 758/758 (100.0%) |
| Ask price match | 806/806 (100.0%) |
| Both match | 100.0% |
| Bid=Ask volume same tick | 618/618 (100.0%) |
| Volume in range [10, 15] | 100.0% |
| Volume uniform chi-sq p | 0.542 (passes) |
| Presence rate | 946/1000 (94.6%) |

## Statistical Tests

- Volume uniformity chi-squared: p = 0.542 -- cannot reject uniform [10, 15].
- Bid/ask offset symmetry: both sides use `round` op with offset=8. Symmetric by construction.
  Spread is always 16 (both sides round identically, so no fractional spread variation).
- Zero misses on either side. Perfect calibration.

## Bot 2 Properties

- Presence: 94.6% of timestamps (structural finding: NOT always present, unlike tomatoes Bot 2)
- Spread: always 16 (symmetric round -- no fractional variation)
- Offset from FV: 8 nominal on both sides (effective offset = 8 + round correction)
- Symmetric: yes (same op and offset both sides)
- Volume: uniform random [10, 15], independent of FV, identical both sides per tick
- No memory: quotes depend only on current FV

### Structural Finding: Partial Presence

Tomatoes Bot 2 was always present (100%). OSMIUM Bot 2 is present 94.6% of timestamps
(946/1000). The 54 absent timestamps may reflect a different scheduling/activation rule
for this product, or a probabilistic quoting model. For simulation, presence_rate=0.946
should be modeled (e.g., Bernoulli draw per tick with p=0.946).
