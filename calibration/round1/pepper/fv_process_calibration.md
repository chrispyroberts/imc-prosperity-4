# FV Process Calibration - INTARIAN_PEPPER_ROOT

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
| Fixed | 5873.80 | -2424.55 | 0.000 |
| DriftingWalk | -51.37 | +178.36 | 1.000 |
| MeanRevertOU | -51.39 | +177.21 | 1.000 |

Lower AIC is better. Higher held-out LL is better. Ljung-Box p > 0.05 means
residuals indistinguishable from white noise.

## Selected Model

**DriftingWalk**

MeanRevertOU has a negligibly-lower AIC (0.023 better, well inside noise).
But held-out LL favors DriftingWalk by 1.15 nats, and by the principle of
parsimony (one fewer effective parameter - OU needs `center`, drift does not)
DriftingWalk is the right choice. Fixed is eliminated decisively: AIC worse
by ~5925 units and Ljung-Box p=0.

On the OU fit the bootstrap gave `kappa` estimates that straddle zero
(near-unidentified), which is the tell-tale sign of an overfit: OU collapses
to DriftingWalk when kappa -> 0 and the model is fitting noise.

## Parameters

| Param | Point estimate | Posterior mean | Posterior std |
|---|---|---|---|
| initial | 12006.000 | 12006.000 | 0.000 |
| drift | 0.09103 | 0.09067 | 0.00932 |
| sigma | 0.2318 | 0.1852 | 0.1467 |

Over 1000 ticks the drift accumulates to ~91 units, matching the observed
first-to-last move (12006 -> 12100). The bootstrap std on drift is 0.009
(10 percent relative), so the drift is well-pinned.

Posterior `sigma` mean (0.185) is notably lower than the point estimate (0.232)
with big std (0.147). This hints at heteroscedasticity: the bootstrap of
residual blocks produces draws with genuinely different noise levels across
segments of the day-0 series. Downstream Monte Carlo should use the
posterior mean plus std and sample accordingly rather than fixing sigma.

## Residual Diagnostics

- Ljung-Box on one-step DriftingWalk residuals (20 lags): **p = 1.000**.
  Residuals are essentially indistinguishable from white noise; the random
  walk plus drift captures the autocorrelation structure perfectly on
  server FV.

## Historical Mid-price Cross-check

| Day | n | Model selected | drift | sigma | Ljung-Box p |
|---|---|---|---|---|---|
| -2 | 9984 | drifting_walk | 0.10047 | 2.82 | 0.000 |
| -1 | 9983 | drifting_walk | 0.10013 | 3.12 | 0.000 |

Model selection is **identical** across all three days (DriftingWalk wins).
Drift is remarkably stable:
- Day -2: 0.10047 per tick
- Day -1: 0.10013 per tick
- Day  0: 0.09103 per tick (server FV)

Days -2 and -1 are within 0.001 of each other. Day 0 is about 10 percent
lower, which could be sampling noise on 670 ticks or a genuine regime shift.
The bootstrap std on day-0 drift (0.009) includes the historical value
within ~1 sigma, so no rejection.

`sigma` is about 12x larger on historical mid (2.8-3.1) than server FV
(0.23). Same interpretation as OSMIUM: mid_price carries microstructure
noise that server FV smooths away. Use the server-FV sigma for Monte Carlo,
not the historical one.

The day -2/-1 Ljung-Box p=0 means the raw mid_price has significant
autocorrelation on top of the drift - consistent with microstructure
bid-ask bounce. On the smoother server FV this effect is washed out.

## Interpretation

PEPPER is a deterministic up-drift of ~0.1 per tick with small gaussian
noise. Over a day (10000 ticks) it moves ~1000 units up. This is not a
tradable signal from a long-the-drift perspective because the sign is
unpredictable at session start (could flip), but it is a massive edge once
you know it: the current price is *systematically* below the fair value
that will be realized in ~100 ticks (expected +10). That is the asymmetric
edge Chrispy's "process that fits" hint points at.

Two non-obvious takeaways:
1. **Drift is persistent across 3 days** (within 10 percent). If the round
   runs new server days, the same drift likely holds.
2. **Server FV is much cleaner than historical mid**. Anyone calibrating
   from CSV alone would fit sigma ~3 and massively overweight noise; calibrating
   from server FV gives the "true" sigma ~0.2 that makes the drift signal
   easy to trade.

## Statistical Tests

- AIC comparison DriftingWalk vs MeanRevertOU: 0.023 apart (tie; pick
  simpler model by parsimony).
- AIC comparison DriftingWalk vs Fixed: Fixed worse by 5925 units (utterly
  decisive).
- Ljung-Box residual whiteness: p = 1.000 (pass).
- Drift stability across days -2, -1, 0: 0.1005, 0.1001, 0.0910. Std across
  days = 0.005; within-day bootstrap std on day 0 = 0.009. The day-0 drift
  is consistent with the other days at the 1 sigma level.
