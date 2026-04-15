# Round 1 Migration Notes

## What Changed Architecturally

- **Products are now config-driven.** The Rust simulator no longer hardcodes product names or per-product constants. Product definitions (FV process, bot quote rules, taker flow, posteriors) live in `configs/<round>.toml`.
- **New ProductConfig schema** in `rust_simulator/src/config.rs` with `Distribution` / `ParametricDist` types supporting scalar values and parametric families.
- **Per-session parameter sampling** via `ProductConfig::sample_from_posterior` draws concrete parameters from the posterior each session. `--fixed-params` disables this.
- **DRO evaluation** (`--dro`) samples adversarial parameters from a widened posterior and reports worst-case PnL per session.

## If You Wrote a Trader That Hardcoded Product Names

Likely safe. The runtime trader contract is unchanged (`Trader.run(state)`). Your trader reads products from `state.order_depths.keys()` and acts on them. If you hardcoded `"EMERALDS"` / `"TOMATOES"` strings, they still appear in tutorial.toml so tutorial-mode behavior is identical. Round 1 traders must adapt to `"ASH_COATED_OSMIUM"` and `"INTARIAN_PEPPER_ROOT"`.

## Deprecated Flags

These Python CLI flags are accepted but emit a deprecation warning:

- `--fv-mode` - behavior now comes from `fv_process.model` in TOML
- `--trade-mode` - same
- `--tomato-support` - tomatoes no longer special-cased

They will be removed in a future release.

## Adding a Product for Round 2+

1. Submit a hold-1 trader (copy and adapt `trader_hold1_round1.py`) to recover server FV for the new product.
2. Copy `calibration/round1/` to `calibration/round2/` and update paths.
3. Run the analyzers per product; write `bot{1,2,3}_calibration.md` and `fv_process_calibration.md`.
4. Extend `calibration/round2/scripts/emit_config.py` to consolidate into `configs/round2.toml`.
5. Run `prosperity4mcbt your_trader.py --round 2 --quick`.

If the new product's bots don't fit the existing archetype (asymmetric offsets, conditional presence, state dependence, novel archetype), see the "What counts as a structural bot difference" section of the design spec at `docs/superpowers/specs/2026-04-15-round1-mc-backtester-design.md`. Those cases require extending the Rust `config.rs` enums and structs.

## Known Findings from Round 1 Calibration

### OSMIUM (ASH_COATED_OSMIUM)

**Fair Value Process**
- Model: Ornstein-Uhlenbeck (mean-reversion)
- Center: 9999.250
- Kappa (reversion rate): 0.0392
- Sigma (volatility): 0.443
- Half-life: 17.7 ticks (mean-reversion timescale)
- Ljung-Box whiteness test: p = 0.284 (residuals are white noise)

Interpretation: OSMIUM is a classic mean-reverting process anchored at ~10000 with slow drift (20-tick reversion timescale) and tight noise. The correct strategy is quote-both-sides around 10000 and lean against the bound when FV is off-center.

**Bot 1 (Outer Wall)**
- Bid: `floor(FV) - 10`
- Ask: `ceil(FV) + 10`
- Volume: uniform [20, 30], same both sides
- Presence: ~80% of timestamps
- Spread: 20 (integer FV) or 21 (fractional FV, ~99% of ticks)
- Symmetric: yes
- Bid/ask match rate: 99.6% / 100.0%

**Bot 2 (Inner Wall)**
- Bid: `round(FV) - 8`
- Ask: `round(FV) + 8`
- Volume: uniform [10, 15], same both sides
- Presence: 94.6% of timestamps (STRUCTURAL FINDING: partial presence, unlike tomatoes)
- Spread: always 16
- Symmetric: yes
- Match rate: 100.0% both sides

**Bot 3 (Inside Quotes)**
- Presence: 7.7% of timestamps
- Always single-sided (never both bid and ask in same tick)
- Side split: 50/50 (40 bid / 39 ask out of 79 events)
- Delta distribution: bimodal at {-3, -2} and {+1, +2} (not uniform)
- Delta offsets: {-3: 23%, -2: 20%, 0: 1%, +1: 23%, +2: 33%}
- Crossing volumes: [4, 10] mean 7.4
- Passive volumes: [1, 6] mean 3.6
- Price rule: `round(FV) + delta`

### PEPPER (INTARIAN_PEPPER_ROOT)

**Fair Value Process**
- Model: Drifting walk (random walk with drift)
- Initial: 12006.000
- Drift: 0.0910 per tick (~910 units per 10k ticks = ~910 per day)
- Sigma (volatility): 0.232 (point estimate), posterior mean 0.185
- Ljung-Box whiteness test: p = 1.000 (perfect whiteness)
- Drift stability across days -2, -1, 0: 0.10047, 0.10013, 0.09103 (within 1 sigma, stable)

Interpretation: PEPPER drifts deterministically upward at ~0.091 per tick. This is a massive edge once recognized: the current price is systematically below the fair value realized in ~100 ticks (expected +10). The signal is not tradable from long-the-drift alone because the sign is unpredictable at session start, but it is a dominant structural feature.

**Bot 1 (Outer Wall)**
- Bid: `ceil(FV) - 10`
- Ask: `floor(FV) + 10`
- Volume: uniform [20, 30], same both sides
- Presence: ~80% of timestamps
- Spread: 13 (fractional FV) or 14 (integer FV)
- Symmetric: yes (same offset, ceil/floor pairing)
- Match rate: 99.8% / 100.0%

Note: PEPPER uses ceil/floor opposite OSMIUM (ceil on bid, floor on ask vs floor/ceil).

**Bot 2 (Inner Wall)**
- Bid: `ceil(FV) - 7`
- Ask: `floor(FV) + 7`
- Volume: approximately uniform [8, 12], same both sides
- Presence: 96.1% of timestamps (STRUCTURAL FINDING: partial presence, unlike tomatoes)
- Spread: 13 (fractional FV) or 14 (integer FV)
- Symmetric: same offset (7) both sides; ops match Bot 1 (ceil bid, floor ask)
- Match rate: 100.0% / 99.9%

**Bot 3 (Inside Quotes)**
- Presence: 4.8% of timestamps (lower than OSMIUM 7.7%)
- Always single-sided
- Side split: 50/50 (21 bid / 28 ask out of 49 events)
- Delta distribution: bimodal at {-4, -3} and {+2, +3, +4} (larger offsets than OSMIUM)
- Delta offsets: {-5: 4%, -4: 27%, -3: 16%, 0: 2%, +2: 22%, +3: 25%, +4: 4%}
- Crossing volumes: [3, 8] mean 5.3
- Passive volumes: [5, 13] mean 9.0 (NOTE: inverted vs OSMIUM; passive here is larger)
- Price rule: `round(FV) + delta`

Sample size: 49 events. Treat with lower confidence than OSMIUM.

### Key Structural Findings

1. **Both Bot 2s have partial presence** (OSMIUM 94.6%, PEPPER 96.1%), unlike tomatoes Bot 2 which was always present. This is a structural difference that must be modeled in simulation (Bernoulli draw per tick).

2. **PEPPER's rounding convention differs from OSMIUM.** PEPPER uses ceil/floor consistently (ceil on bid, floor on ask); OSMIUM uses floor/ceil for Bot 1 and round for Bot 2. This is not a bug; it's how the server encodes each product.

3. **PEPPER Bot 3 passive volumes are larger than crossing volumes.** This is inverted vs OSMIUM (and tomatoes) and may indicate a different bot archetype. Confidence is lower on PEPPER Bot 3 due to only 49 events.

4. **FV drift is massively different.** OSMIUM mean-reverts around 10000 (half-life 17.7 ticks); PEPPER drifts steadily upward (0.091 per tick, ~910 per day). A strategy that works for both must handle this regime difference.
