# Bot 3 Calibration -- INTARIAN_PEPPER_ROOT

## Method

Bot 3 is identified by the classifier as any book level with |offset from FV| < 5.0
(inside Bot 2's inner threshold). Same approach as the tomatoes template.

Inputs: `calibration/round1/data/fv_and_book_intarian_pepper_root.json`
Script: `calibration/round1/pepper/scripts/analyze_bot3.py`

## Key Findings

| Property | Value |
|---|---|
| Presence | 48/999 timestamps (4.8%) |
| Events | 49 total book levels tagged bot3 |
| Both-sided timestamps | 0 (always single-sided) |
| Side split | 21 bid / 28 ask |
| Side 50/50 p-value | 0.32 (not significant; consistent with 50/50) |
| Delta support | {-5, -4, -3, 0, +2, +3, +4} |
| Delta counts | {-5: 2, -4: 13, -3: 8, 0: 1, +2: 11, +3: 12, +4: 2} |
| Delta uniform p-value | 0.0007 (NOT uniform; bimodal at -4/-3 vs +2/+3) |
| Crossing n | 28 (bid above FV or ask below FV) |
| Crossing vol range | [3, 8] mean 5.3 |
| Passive n | 21 (bid below FV or ask above FV) |
| Passive vol range | [5, 20] mean 9.0 |

## Structural Notes

WARNING: 49 events total (48 timestamps) is above 30 but marginal for robust calibration.
The passive and crossing distributions here are inverted relative to tomatoes and osmium.
Passive orders have LARGER volumes (mean 9.0, range 5-20) while crossing orders have
SMALLER volumes (mean 5.3, range 3-8). This could indicate a different bot archetype
or a small-sample artifact.

The delta distribution is bimodal, not uniform: positive offsets at +2/+3/+4 and
negative offsets at -3/-4/-5. Offsets are consistently larger than osmium (1-3 vs 2-4
from FV), consistent with pepper having wider spreads.

Two ts=0 events (price 12006 and 12009 from FV=12006) are flagged as bot3 at tick 0.
The qty=20 event (delta=+3, passive) is a likely outlier inflating passive mean.

## Statistical Tests

**Side split (50/50 null):** 21 bid / 28 ask out of 49 events. z = 1.00, p = 0.32.
Cannot reject 50/50. Model as Bernoulli(0.5).

**Delta uniform (chi-sq):** p = 0.0007. Reject uniformity. Distribution is bimodal:
negative offsets peak at -4, positive offsets peak at +2/+3. For simulation use
discrete weights or simplify to uniform over {-4, -3, +2, +3}.

## Rust Simulation Rule

```
if rand < presence_rate:
    side = random(bid, ask)  // 50/50
    delta = random_choice({-5: 0.04, -4: 0.27, -3: 0.16, 0: 0.02, +2: 0.22, +3: 0.25, +4: 0.04})
    price = round(fv) + delta
    if (side == bid and price > fv) or (side == ask and price < fv):
        vol = Uniform(3, 8)    // crossing (mean 5.3)
    else:
        vol = Uniform(5, 13)   // passive (cap at 13; qty=20 outlier excluded)
```

Presence beta posterior: Beta(49, 952) -- use for sampling presence_rate.

## Sample Size Warning

49 events / 48 timestamps is above 30 but marginal. The passive volume distribution
(mean 9.0, range 5-20) is unusual and may be dominated by a few large outliers.
Treat pepper bot3 calibration with lower confidence than osmium. If additional data
becomes available, re-run the analysis.
