# Calibration Analysis Philosophy

## The Cardinal Rule: Never Look at Marginals

When reverse-engineering a data-generating process, **never examine a variable in isolation**. Always condition on every other known variable.

If you have variables (side, price, volume, timing), you must check:
- volume | price
- volume | side
- volume | (side, price)
- price | side
- timing | price
- etc.

The marginal distribution hides structure that the conditional reveals. A "uniform [2, 12]" volume distribution might actually be two completely different processes — aggressive orders at [5, 12] and passive orders at [2, 6] — that only become visible when you condition on price relative to fair value.

## Why This Matters

Every number in the data is the output of a decision process. The bot decides WHERE to place the order first, and that decision determines the context for HOW MUCH. Aggregating volume across all prices is like averaging the height of adults and children and calling it "human height."

## The Workflow

For each bot / behavior:
1. Identify the primary variable (usually price placement relative to FV)
2. Condition EVERY other variable on the primary variable
3. Look for splits: does the distribution change across conditions?
4. If yes, that's a structural feature of the bot's algorithm — model it
5. If no, it's truly independent — model it as independent
6. Never declare a model "done" until every pairwise conditional has been checked

## Never Trust Eyeballed Distributions

When a distribution doesn't look exactly uniform or 50/50, **run the stat test before concluding it's non-uniform**. Small samples produce lopsided-looking splits all the time.

- A 55/45 split with n=242 has p=0.14 — completely consistent with 50/50.
- A 46/54 split with n=125 has p=0.47 — noise.
- A 66/34 split with n=1450 has p≈0 — real structure.

The rule: compute chi-squared or a z-test. If p > 0.05 (with Bonferroni correction for multiple tests), the simpler model wins. Don't hardcode a parameter from noise.

Corollary: when you DO find structure (like the 2/3 passive vs 1/3 aggressive split), verify it's consistent across multiple days and subsamples before declaring it real. A pattern that appears in 2+ independent days is much more credible than one that only shows up in a single sample.
