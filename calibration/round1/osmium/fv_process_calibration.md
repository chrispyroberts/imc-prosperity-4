# FV Process Calibration - ASH_COATED_OSMIUM

## Method

Fit three candidate processes (Fixed, DriftingWalk, MeanRevertOU) on day-0
server FV (first 67 percent = 670 ticks) with held-out log-likelihood on the
last 33 percent (330 ticks). Non-parametric bootstrap (500 draws) gives a
posterior over parameters. Cross-check on historical `mid_price` for days -2
and -1 from the CSV dumps, fit per-day to avoid the fake day-boundary jump.

Server FV is the price derived from the hold-1 trader's pnl, which recovers
exactly the server's internal fair value for Bot-1 products. Historical
`mid_price` is noisier because it mixes Bot-2 and Bot-3 quote asymmetry.

## Candidates Tested

| Model | Train AIC | Held-out LL | Ljung-Box p |
|---|---|---|---|
| Fixed | 2960.45 | -717.98 | 0.000 |
| DriftingWalk | 839.82 | -113.11 | 0.877 |
| MeanRevertOU | 817.01 | -113.09 | 0.284 |

Lower AIC is better. Higher held-out LL is better. Ljung-Box p > 0.05 means
residuals indistinguishable from white noise.

## Selected Model

**MeanRevertOU**

AIC gap over DriftingWalk is 22.8 (strongly significant: delta-AIC > 10
corresponds to a likelihood ratio exceeding ~150:1). Held-out LL is within
0.02 nats of DriftingWalk, so both generalize equally well on the last 330
ticks, but OU explains the training set meaningfully better. Fixed is
eliminated: both AIC (~2000 worse) and Ljung-Box (p=0) reject it decisively,
confirming OSMIUM's FV is not a constant plus iid noise.

## Parameters

| Param | Point estimate | Posterior mean | Posterior std |
|---|---|---|---|
| center | 9999.250 | 9999.226 | 0.445 |
| kappa | 0.03920 | 0.04106 | 0.00877 |
| sigma | 0.4430 | 0.4347 | 0.1017 |
| initial | 10011.000 | 10011.000 | 0.000 |

Half-life of mean-reversion at kappa=0.039 is `ln(2) / kappa` which is 17.7
ticks. OSMIUM relaxes back to center on a ~20-tick timescale.

## Residual Diagnostics

- Ljung-Box on one-step OU residuals (20 lags): **p = 0.284** -> residuals
  pass the whiteness test at the 5 percent level. The OU model's
  autocorrelation structure is adequate.
- DriftingWalk residuals also pass (p=0.877), indicating the two models are
  empirically hard to distinguish on short server-FV samples. OU is picked
  because AIC strongly favors it and the steady-state center at 9999.25 is
  exactly the 10000 target that community chatter hinted at (OSMIUM
  "oscillates around ~10000").

## Historical Mid-price Cross-check

| Day | n | Model selected | center | kappa | sigma | Ljung-Box p |
|---|---|---|---|---|---|---|
| -2 | 9982 | mean_revert_ou | 9998.16 | 0.2608 | 3.51 | 0.000 |
| -1 | 9983 | mean_revert_ou | 10000.83 | 0.3494 | 3.38 | 0.000 |

Same model family wins on all three days, and the `center` parameter is
stable at ~9998-10001 across all three days. Two things diverge:

1. `kappa` is ~7x larger on historical mid (0.26-0.35) vs server FV (0.039).
   The historical mid-price flips 1 tick up-and-down every step (microstructure
   bid-ask bounce), which looks like very fast reversion. Server FV smooths
   this out, so the slower "fundamental" reversion kappa=0.04 is what the
   monte-carlo should use.
2. `sigma` is ~8x larger on mid (3.4-3.5) vs server FV (0.44). Same reason:
   mid-price noise includes microstructure that server FV removes.
3. Ljung-Box p=0 on historical mid: the bid-ask bounce autocorrelation
   violates pure AR(1). Server FV passes the test so server-FV-based OU is
   the right calibration target.

## Interpretation

OSMIUM is a classic Ornstein-Uhlenbeck process anchored at 10000. The slow
pull (kappa=0.04, half-life ~18 ticks) and tight sigma=0.44 mean the server's
FV drifts around the center slowly and never wanders more than ~10 ticks.
This matches Chrispy's and the Discord's "rolling average around 10000"
intuition exactly: the correct strategy is quote-both-sides around 10000 and
lean against the bound when FV is off-center.

The mean-reversion gives a free signal: when FV is below center, expected
next-step move is up, and vice versa.

## Statistical Tests

- AIC comparison: MeanRevertOU wins over DriftingWalk by 22.8 units (>10 is
  decisive per Burnham-Anderson).
- AIC comparison vs Fixed: MeanRevertOU wins by 2143 units (utterly decisive).
- Ljung-Box residual whiteness: p = 0.284 (pass).
- Parameter stability across days: `center` within 2.7 of 10000 on all three
  days (tight); `kappa` varies 0.04-0.35, explained by microstructure
  difference between server FV and raw mid-price.
