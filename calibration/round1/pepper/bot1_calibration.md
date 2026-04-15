# Bot 1 (WALL) Calibration -- INTARIAN_PEPPER_ROOT

## Method

Same pattern as TOMATOES Bot 1 calibration (`calibration/tomatoes/bot1_calibration.md`).
Source: hold-1 submission (day 0 website test run, 1000 ticks).

Bot 1 levels identified as `|offset from FV| >= 8.5`, using thresholds in
`calibration/round1/scripts/classify_levels.py`.

Brute-force search over `{floor, ceil, round}(FV + shift) +/- offset` for all
shifts in {-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1} and offsets in [5, 19].

## Result

```python
bid = ceil(FV) - 10      # equivalent: ceil(FV - 1.0) - 9
ask = floor(FV) + 10     # equivalent: floor(FV - 1.0) + 11
vol = randint(15, 25)    # same value for bid and ask on each tick
```

Rust rule strings (used by `products.rs::quote_price_for_rule`):
- bid: `ceil_fv_minus_offset`, offset=10
- ask: `floor_fv_plus_offset`, offset=10

### Structural note: PEPPER vs OSMIUM rounding direction

OSMIUM uses floor/ceil (bid=floor, ask=ceil), which WIDENS the spread for fractional FV
(spread ~21 for FV = X.Y, Y > 0).

PEPPER uses ceil/floor (bid=ceil, ask=floor), which NARROWS the spread for fractional FV
(spread ~19 for FV = X.Y, Y > 0).

Both products use nominal offset=10 -- the integer argument passed to the rule.
The structural difference is the choice of rounding operation, not the offset magnitude.

Since bid and ask use DIFFERENT ops (ceil vs floor), the bid/ask offsets from FV are
not identical for non-integer FV:
- bid offset magnitude: ceil(FV) - 10 - FV = ceil(FV) - FV - 10 = (1 - frac(FV)) + ... 
  for FV=X.Y: bid = X+1-10 = X-9, offset_mag = FV-(X-9) = 9+Y (where Y=frac(FV))
- ask offset magnitude: floor(FV)+10 - FV = 10 - Y

The bid magnitude (9+Y) differs from ask magnitude (10-Y) by ~1 for Y=0.5.
This is a rounding asymmetry, not a structural offset asymmetry.
The nominal integer offset is 10 on both sides -- bots.json uses `offset=10`.

**Flag for Task 18 / future tasks**: if `Bot1Params` in Rust has a single `offset`
field, that is sufficient for both products (both use offset=10). No `bid_offset`
/ `ask_offset` split needed for this calibration. The rule string encodes the op.

## Validation

| Metric | Score |
|---|---|
| Bid price match | 804/805 (99.9%) |
| Ask price match | 795/796 (99.9%) |
| Both match (min) | 99.9% |
| Bid=Ask volume same tick | 640/640 (100.0%) |
| Volume in range [15, 25] | 100.0% |
| Volume uniform chi-sq p | 0.006 (rejects strict uniformity) |

## Statistical Tests

- Volume uniformity chi-squared: p = 0.006 -- rejects strict uniform at alpha=0.05.
  Inspection shows mild humps at 23 and 25 (each ~90 vs ~65 expected). This may be
  a bimodal or U-shaped distribution rather than pure uniform, but the [15, 25] range
  is correct. For simulation purposes, uniform [15, 25] is a reasonable model; a more
  precise fit would use empirical counts.
- Bid/ask offset symmetry: both sides use the same integer offset=10. The rounding
  ops differ (ceil on bid, floor on ask) producing spread=19 for fractional FV.
  This is NOT an asymmetric wall; it is a different-direction rounding scheme.
- Bid miss at ts=0: anomalous opening tick with fv=12006.0 (integer) where the actual
  bid was 11991 (5 below prediction). Opening tick artifact, not structural.
- Ask miss at ts=1000: fv=12001.0 (integer), actual ask 12010 vs predicted 12011 (off by 1).
  Integer-FV rounding ambiguity (same class as TOMATOES misses).

## Bot 1 Properties

- Presence: approx 80% of timestamps (some ticks have only one side or no bot1)
- Spread: 19 (fractional FV, ~99% of ticks) or 20 (integer FV)
- Offset from FV: ~9.5 mean (ceil/floor narrows vs OSMIUM floor/ceil)
- Symmetric: yes in terms of integer offset (10 on both sides); ops differ
- Volume: uniform-ish [15, 25] with mild humping at 23, 25; independent of FV; identical both sides per tick
- No memory: quotes depend only on current FV
