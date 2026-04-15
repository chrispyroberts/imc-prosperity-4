# Bot 3 Calibration -- ASH_COATED_OSMIUM

## Method

Bot 3 is identified by the classifier as any book level with |offset from FV| < 5.0
(inside Bot 2's inner threshold). Same approach as the tomatoes template.

Inputs: `calibration/round1/data/fv_and_book_ash_coated_osmium.json`
Script: `calibration/round1/osmium/scripts/analyze_bot3.py`

## Key Findings

| Property | Value |
|---|---|
| Presence | 77/998 timestamps (7.7%) |
| Events | 79 total book levels tagged bot3 |
| Both-sided timestamps | 0 (always single-sided) |
| Side split | 40 bid / 39 ask |
| Side 50/50 p-value | 0.91 (not significant; consistent with 50/50) |
| Delta support | {-3, -2, 0, +1, +2} |
| Delta counts | {-3: 18, -2: 16, 0: 1, +1: 18, +2: 26} |
| Delta uniform p-value | 0.0003 (NOT uniform; bimodal at -3/-2 vs +1/+2) |
| Crossing n | 32 (bid above FV or ask below FV) |
| Crossing vol range | [4, 10] mean 7.4 |
| Passive n | 47 (bid below FV or ask above FV) |
| Passive vol range | [1, 13] mean 3.6 |

## Structural Notes

The delta distribution is bimodal, not uniform: positive offsets cluster at +1/+2
and negative offsets cluster at -2/-3. This differs from the tomatoes pattern where
{-2,-1,0,+1} was approximately uniform. Practically both describe "a random integer
1-3 ticks from FV on either side."

The wide passive volume range [1, 13] with mean 3.6 suggests the lower end
(1-6) dominates but a few outliers extend the range. Tomatoes passive was [2,6].
For simulation, capping passive at U(1, 6) is reasonable given the mean.

Crossing volumes [4, 10] with mean 7.4 align closely with tomatoes [5, 12] mean 8.1.

## Statistical Tests

**Side split (50/50 null):** 40 bid / 39 ask out of 79 events. z = 0.11, p = 0.91.
Cannot reject 50/50. Model as Bernoulli(0.5).

**Delta uniform (chi-sq):** observed {-3: 18, -2: 16, 0: 1, +1: 18, +2: 26}.
p = 0.0003. Reject uniformity. The true distribution is bimodal: mostly +-2 to +-3
with a small number at 0 and +1. For simulation use a discrete weighted distribution
or simplify to uniform over {-2, -1, +1, +2} (dropping rare 0 and -3 extremes).

## Rust Simulation Rule

```
if rand < presence_rate:
    side = random(bid, ask)  // 50/50
    delta = random_choice({-3: 0.23, -2: 0.20, 0: 0.01, +1: 0.23, +2: 0.33})
    price = round(fv) + delta
    if (side == bid and price > fv) or (side == ask and price < fv):
        vol = Uniform(4, 10)   // crossing
    else:
        vol = Uniform(1, 6)    // passive (cap at 6 to trim outliers)
```

Presence beta posterior: Beta(78, 922) -- use for sampling presence_rate.

## Sample Size Note

79 events (77 timestamps) is above the 30-event threshold. Statistics are meaningful
but the delta distribution details should be treated with moderate confidence.
