# Round 1 Calibration Findings

A cross-cutting summary of what the per-bot, per-product, and per-process
calibration revealed about IMC Prosperity 4 Round 1 market microstructure.
Per-bot detail lives in the individual markdowns under
`calibration/round1/{osmium,pepper}/`; this document stitches those findings
into a narrative, calls out structural surprises, and translates each
finding into an actionable trading implication.

Source: hold-1 submission 157932 (day 0, 1000 ticks) plus the historical
day -2 / day -1 mid-price CSVs as a stability cross-check.

## Products and positioning

| Product | Position limit | FV regime | Community strategy |
|---|---:|---|---|
| `ASH_COATED_OSMIUM` | 80 | mean-reverts around 10000 | market-make with tight spread |
| `INTARIAN_PEPPER_ROOT` | 80 | linearly drifts up ~91/day | buy-and-hold to position limit |

Position limit 80 per product per the Discord admin confirmation and the
wiki. Currency label is `XIRECS` (no trading-floor impact beyond label).

## Headline finding: server fair value is much smoother than mid-price

Measured on day 0 server FV vs observed mid-price across all 1000 ticks:

| Product | Server-FV step std | Mid-price step std | Ratio |
|---|---:|---:|---:|
| `ASH_COATED_OSMIUM` | 0.443 | 3.51 | 7.9x |
| `INTARIAN_PEPPER_ROOT` | 0.232 | 2.82 | 12.2x |

The server computes PnL against a continuous, quantized 1/2048 fair value
that is NOT the order-book mid. Mid-price carries bid-ask bounce noise that
the server's internal FV smooths away.

**Trading implication.** Any signal that treats mid-price as FV is fighting
8-12x more noise than signals built against the recovered server FV. The
clean way to estimate server FV in live trading is to use the Bot 1 wall
midpoint, since Bot 1 quotes symmetrically around server FV at a known
offset.

For OSMIUM (Bot 1 rule: `floor(FV) - 10` and `ceil(FV) + 10`):

```
fv_estimate = (bot1_bid_price + bot1_ask_price) / 2
            = (floor(FV) + ceil(FV)) / 2
            = FV when FV is integer, else FV_int + 0.5
```

This recovers integer-granularity server FV. Fractional part has to come
from Bot 2's asymmetric rounding or from a rolling regression against
observed PnL if the trader is holding a position.

## OSMIUM fair-value process (MeanRevertOU)

Selected by AIC + held-out log-likelihood (training = first 67% of day 0,
held-out = last 33%):

| Model | AIC | Held-out LL | Ljung-Box p |
|---|---:|---:|---:|
| Fixed | 2960 | -717.98 | 0.000 |
| DriftingWalk | 839.8 | -113.11 | 0.877 |
| MeanRevertOU | **817.0** | **-113.09** | 0.284 |

MeanRevertOU wins by AIC by 23 units over DriftingWalk and held-out LLs
are essentially tied. Residuals pass Ljung-Box whiteness test at p=0.28 so
the process is adequate.

```
x_{t+1} = x_t - 0.0392 * (x_t - 9999.25) + N(0, 0.443^2)
```

Posterior (bootstrapped):
- center: 9999.23 ± 0.45
- kappa: 0.0411 ± 0.0088
- sigma: 0.435 ± 0.102

**Half-life of a deviation is `ln(2) / -ln(1 - kappa) ≈ 17.7 ticks`.** A
dislocation of size D at time t decays to D/2 by roughly t+18 in
expectation.

Historical cross-check on days -2 and -1 mid-prices also selects OU with
the same center (9998.2 / 10001.0) and similar qualitative kappa/sigma,
though absolute levels are inflated by mid-price noise. **The model is
structurally stable across days.**

**Trading implication.** At any point, `fair - center` is a mean-reverting
signal with a measured speed. If the OSMIUM mid gaps to 10005, the
equilibrium-driven expected drift to 9999 over the next 18 ticks is
5 / e^(0.0392 * 18) ≈ 5 * 0.495 ≈ 2.48 — a clean, statistically-rooted
expected reversion. A 10-tick or 20-tick rolling-average crossover strategy
is approximately the right time scale. Community Discord's "rolling
averages" alpha hint for OSMIUM is consistent with this OU half-life.

## PEPPER fair-value process (DriftingWalk)

| Model | AIC | Held-out LL | Ljung-Box p |
|---|---:|---:|---:|
| Fixed | 5874 | -2424.55 | 0.000 |
| DriftingWalk | -51.37 | 178.36 | 1.000 |
| MeanRevertOU | -51.39 | 177.21 | 1.000 |

OU nominally ties DW but OU's kappa collapses toward 0 when fit, so they
are the same model; DriftingWalk wins by parsimony. Ljung-Box p=1.0 means
residuals are indistinguishable from pure white noise.

```
x_{t+1} = x_t + 0.0910 + N(0, 0.232^2)
```

Posterior:
- drift: 0.0907 ± 0.0093 per tick
- sigma: 0.185 ± 0.147 (heteroscedastic across segments)

Day 0 drift of 0.091/tick * 1000 ticks ≈ 91 per day.

Historical cross-check: day -2 and -1 mid-price fits give drift of 0.1005
and 0.1001. Remarkably consistent. **Drift is stable at about 0.09-0.10
per tick across all three observed days.** The sigma shown for historical
days is inflated by mid-price bounce; when calibrated against a
hold-1-equivalent server FV it would match the day-0 estimate.

**Trading implication.** Pure buy-and-hold from t=0 to day end captures
the full drift at the price of volatility exposure. With position limit 80
and expected drift of 91 per day, the carry is 80 * 91 = 7280 XIRECS in
expectation on day 1 if the drift remains stable — matching the Discord
community's ~7300 buy-hold benchmark.

Alternatively, rebalanced momentum strategies can harvest the same drift
with smaller inventory and thus smaller mark-to-market variance. Since the
drift is linear (not accelerating), the simplest robust harvester is to
hit position limit by t=0 (saturated long) and hold.

Risk: this is the highest-conviction trade on Round 1 training data, which
also makes it the highest overfit surface. The `--dro` evaluation will
widen the drift posterior and show worst-case PnL if day-1 drift is
significantly lower than 0.09.

## Bot 1 calibration (outer wall)

Quote rules and volumes per product. Every row is chi-sq validated; rules
matched >99.6% on both products.

| Product | Bid rule | Ask rule | Offset | Volume range | Presence | Bid match | Ask match |
|---|---|---|---:|---|---:|---:|---:|
| OSMIUM | `floor(FV) - 10` | `ceil(FV) + 10` | 10 | Uniform[20, 30] | 100% | 99.62% | 100.00% |
| PEPPER | `ceil(FV) - 10` | `floor(FV) + 10` | 10 | Uniform[15, 25] | 100% | 99.88% | 99.87% |

**Note the opposite rounding convention.** OSMIUM widens (floor on bid,
ceil on ask — "outside rounding"); PEPPER narrows (ceil on bid, floor on
ask — "inside rounding"). For a fractional FV like 12000.4, PEPPER Bot 1
places 12001 - 10 = 11991 (bid) and 12000 + 10 = 12010 (ask) for a spread
of 19, while OSMIUM Bot 1 at 10000.4 places 10000 - 10 = 9990 (bid) and
10001 + 10 = 10011 (ask) for a spread of 21.

**Trading implication.** Bot 1 is always present on both sides, with known
volumes. The Bot 1 mid-point `(bot1_bid + bot1_ask) / 2` recovers server FV
to the nearest half-integer. Market-making inside Bot 1's spread is safe
(you capture taker flow between the walls); beating Bot 1 requires going
inside Bot 2 (see below).

Volume asymmetry: OSMIUM Bot 1 averages ~25 units per side vs PEPPER Bot 1
~20 units. Less liquid on PEPPER — consistent with Discord complaints about
"lack of liquidity on pepper".

## Bot 2 calibration (inner wall)

| Product | Bid rule | Ask rule | Offset | Volume range | Presence | Bid match | Ask match |
|---|---|---|---:|---|---:|---:|---:|
| OSMIUM | `round(FV) - 8` | `round(FV) + 8` | 8 | Uniform[10, 15] | 94.6% | 100% | 100% |
| PEPPER | `ceil(FV) - 7` | `floor(FV) + 7` | 7 | Uniform[8, 12] | 96.1% | 100% | 99.87% |

### Structural finding #1: Bot 2 partial presence

Tomatoes Bot 2 was present 100% of ticks. **Round 1 Bot 2 is only present
on ~95% of ticks.** This was not in the original tomatoes-derived rust
model; `configs/round1.toml` captures it as a scalar `presence_rate` field
on `Bot1Params` / `Bot2Params`. The rust simulator's per-tick bot quoting
must respect the presence draw.

**Trading implication.** Bot 2 defines the best bid and ask most of the
time. When Bot 2 is absent, the spread widens from ~16 (osmium) / 13-14
(pepper) to ~20-21 (osmium) / 19-20 (pepper). An MM strategy that posts at
Bot 2's boundary captures taker flow when Bot 2 is present, and when Bot 2
is absent your inside quotes become the best bid / ask — you eat the full
taker spread. Handling the Bot-2-absent case deliberately (either by
widening your own spread or by accepting larger implied fills) is worth
modeling.

### Bot 2 rounding

OSMIUM Bot 2 is symmetric (`round(FV) ± 8`) so its spread is a fixed 16
regardless of FV. PEPPER Bot 2 narrows toward FV (`ceil - 7` / `floor + 7`)
so its spread alternates between 13 (fractional FV) and 14 (integer FV) —
the same shape as tomatoes Bot 2 but reached via different math.

## Bot 3 calibration (rare inside-spread quote)

| Product | Presence | N events | Side split | Delta support | Crossing vol | Passive vol |
|---|---:|---:|---|---|---|---|
| OSMIUM | 7.7% | 79 | 50/50 (p=0.91) | -3,-2,0,+1,+2 | Uniform[4,10] mean 7.4 | [1,6] (capped) |
| PEPPER | 4.8% | 49 | 50/50 (p=0.32) | -5,-4,-3,0,+2,+3,+4 | Uniform[3,8] | [5,13] (capped) |

### Structural finding #2: Bot 3 price-delta distribution is NOT uniform

Tomatoes Bot 3 drew from Uniform {-2, -1, 0, +1}. Both Round 1 products
have bimodal delta distributions with weights:

OSMIUM: `{-3: 0.228, -2: 0.203, 0: 0.013, +1: 0.228, +2: 0.329}`

PEPPER: `{-5: 0.041, -4: 0.265, -3: 0.163, 0: 0.020, +2: 0.224, +3: 0.245, +4: 0.041}`

The near-zero weight at delta=0 on both products means Bot 3 almost never
quotes exactly at FV — it's either placing defensively away from FV or
crossing aggressively. The wider support on PEPPER (max |delta|=5 vs 3 for
OSMIUM) tracks the lower sample size; some tail weight may be noise.

The current `configs/round1.toml` stores the support as a list and the
rust simulator samples uniformly. **For higher fidelity**, the TOML schema
could grow a `price_delta_weights` field and the rust sampler could use
`rand::distributions::WeightedIndex`. Follow-up item.

### Structural finding #3: PEPPER Bot 3 passive volumes exceed crossing volumes

On OSMIUM: crossing mean 7.4, passive capped at mean ~3.6 — same pattern
as tomatoes (aggressive crossers are larger, passive resters are smaller).

On PEPPER: crossing mean 5.3, **passive ranges up to 20 units with mean 9.0**,
higher than crossing. Inverted from the tomatoes pattern. Possibly a
sample artifact (49 events is marginal) but worth re-checking against a
larger sample if available.

**Trading implication.** Bot 3 is too rare (<8%) and too small to rely on
for fills. It adds noise to the book inside Bot 2's spread. For strategy
design purposes it can be treated as ambient noise and monitored rather
than modeled.

## Taker flow

| Metric | OSMIUM | PEPPER |
|---|---:|---:|
| trade_active_prob (per tick) | 4.22% | 3.37% |
| second_trade_prob (given any trade) | 5.25% | 4.01% |
| buy_prob (default, see below) | 0.5 | 0.5 |

Single-tick second-trade rate is low on both products.

### Structural finding #4: buy_prob cannot be inferred from Round 1 CSVs

The Round 1 trades CSVs (`trades_round_1_day_*.csv`) have empty `buyer`
and `seller` columns. Without that attribution, we cannot directly measure
the take direction (buy vs sell).

**Worked around by defaulting to `buy_prob = 0.5` with a Jeffreys prior
Beta(1, 1).** This is unbiased under the assumption that takers are
balanced, which is a reasonable null hypothesis but unverified. Future
signals — e.g., "trade at ask is a buy, trade at bid is a sell" — could
refine this if the mid-price-at-trade-time context lets us classify each
trade.

**Trading implication.** Until we can observe take direction, don't build
an alpha that depends on predicting taker side. Design MM strategies to be
symmetric (same spread capture expectation regardless of direction), and
verify under `--dro` with `buy_prob` widened that your PnL doesn't collapse
under asymmetric taker flow.

## Cross-product correlation

Community Discord measured 0.65 Pearson correlation between OSMIUM and
PEPPER mid-prices on historical days. Not re-measured in this calibration
but worth confirming before building cross-product strategies. 0.65 is too
low to justify static hedging but warrants monitoring for regime shifts.

## Residual diagnostics (model adequacy)

| Product | Model | Ljung-Box p (lag 20) | Adequate? |
|---|---|---:|---|
| OSMIUM | MeanRevertOU | 0.284 | Yes |
| PEPPER | DriftingWalk | 1.000 | Yes (very) |

Both residual series pass the white-noise test. The chosen processes
describe the observed day-0 server FV with no detectable residual
autocorrelation. We are not missing a higher-order process component at
this granularity.

## Known limitations

1. **Single day of server FV** (day 0 only) — the hold-1 submission runs
   on day 0 test data only. Calibration robustness is anchored on 1000
   ticks; parameters could shift on day 1 eval. The bootstrap posterior
   captures parameter uncertainty; `--dro` widens it further for
   worst-case evaluation.

2. **Bot 3 sample sizes** (79 OSMIUM / 49 PEPPER events) make fine-grained
   claims about Bot 3 structure only weakly supported. Chi-sq tests on
   bimodal delta are significant but individual bucket weights could
   shift on day 1.

3. **Taker direction unobservable** — see Structural finding #4. Mitigated
   by symmetric strategy design + DRO widening.

4. **Bot 3 price-delta weights** not yet wired into the rust simulator
   (schema extension needed); rust samples uniformly from the support.
   Uniform approximation loses ~10-15% delta-allocation fidelity. Follow-up.

## Summary of structural deviations from tomatoes

This is what the design spec called out as things to flag if discovered
during calibration, updated with our actual findings:

| Item | Status |
|---|---|
| Asymmetric wall offsets (bid ≠ ask) | Not observed. Both walls symmetric in magnitude. |
| **Asymmetric rounding direction (floor vs ceil)** | **Confirmed on Bot 1.** OSMIUM widens (floor-bid / ceil-ask); PEPPER narrows (ceil-bid / floor-ask). Both products use opposite-direction conventions from each other. |
| **Conditional presence on Bot 2** | **Confirmed.** OSMIUM 94.6%, PEPPER 96.1%. Tomatoes was 100%. |
| Different bot count | Not observed. 3 bot archetypes persist. |
| State dependence (bot quote depends on history) | Not observed. Current-FV-only model fits. |
| New archetype (liquidity taker, time-in-force etc.) | Not observed. |
| **Non-uniform Bot 3 delta** | **Confirmed on both products.** Bimodal with near-zero weight at delta=0. |

The rust `Bot1Params::offset: Distribution` already accommodated all
findings because the bid/ask offsets happened to be symmetric; only the
rule string differs. No rust enum extensions were needed. The
`presence_rate: Distribution` field on Bot 1 / Bot 2 already existed.

## References

- Per-bot detail: `calibration/round1/{osmium,pepper}/bot{1,2,3}_calibration.md`
- FV process detail: `calibration/round1/{osmium,pepper}/fv_process_calibration.md`
- Design spec: `docs/superpowers/specs/2026-04-15-round1-mc-backtester-design.md`
- Migration notes: `docs/ROUND1_MIGRATION.md`
- Methodology: `calibration/ANALYSIS_PHILOSOPHY.md`
