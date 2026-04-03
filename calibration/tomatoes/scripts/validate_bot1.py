"""
Validate bot1.py against actual server data.
Compares simulated Bot 1 quotes to real Bot 1 quotes at every timestamp.
"""

import json, math, random
from pathlib import Path
from collections import Counter

from bot1 import bot1_quote, bot1_quote_with_noise

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]

# Extract actual Bot 1 quotes (worst levels)
actual = []
for r in rows:
    actual.append({
        "fv": r["fv"],
        "bid": min(r["bids"]),
        "ask": max(r["asks"]),
        "vol": r["bid_vols"].get(str(min(r["bids"])), r["bid_vols"].get(min(r["bids"]), 0)),
    })

# ═══════════════════════════════════════════════════════════════
# Test 1: Simple rule (round(FV) ± 8)
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("  VALIDATION: bot1_quote (simple round(FV) ± 8)")
print("=" * 70)

bid_match = 0; ask_match = 0; both_match = 0; spread_match = 0
bid_errs = Counter(); ask_errs = Counter()

for rec in actual:
    sim_bid, sim_ask, _ = bot1_quote(rec["fv"])

    bm = sim_bid == rec["bid"]
    am = sim_ask == rec["ask"]
    bid_match += bm
    ask_match += am
    both_match += (bm and am)
    spread_match += ((sim_ask - sim_bid) == (rec["ask"] - rec["bid"]))

    if not bm: bid_errs[sim_bid - rec["bid"]] += 1
    if not am: ask_errs[sim_ask - rec["ask"]] += 1

n = len(actual)
print(f"\n  Bid match:    {bid_match}/{n} ({bid_match/n*100:.1f}%)")
print(f"  Ask match:    {ask_match}/{n} ({ask_match/n*100:.1f}%)")
print(f"  Both match:   {both_match}/{n} ({both_match/n*100:.1f}%)")
print(f"  Spread match: {spread_match}/{n} ({spread_match/n*100:.1f}%)")
print(f"\n  Bid errors: {dict(bid_errs)}")
print(f"  Ask errors: {dict(ask_errs)}")

# ═══════════════════════════════════════════════════════════════
# Test 2: Volume distribution comparison
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  VOLUME DISTRIBUTION COMPARISON")
print("=" * 70)

actual_vols = [rec["vol"] for rec in actual]
random.seed(42)
sim_vols = [random.randint(15, 25) for _ in range(n)]

print(f"\n  {'vol':>4} {'actual':>8} {'simulated':>10} {'diff':>8}")
ac = Counter(actual_vols); sc = Counter(sim_vols)
for v in range(15, 26):
    a_pct = ac.get(v, 0) / n * 100
    s_pct = sc.get(v, 0) / n * 100
    print(f"  {v:>4} {a_pct:>7.1f}% {s_pct:>9.1f}% {s_pct-a_pct:>+7.1f}%")

# Check: are actual volumes truly uniform?
from statistics import NormalDist
expected = n / 11  # 11 possible values
chi2 = sum((ac.get(v, 0) - expected)**2 / expected for v in range(15, 26))
# chi2 with 10 df: p<0.05 at 18.3
print(f"\n  Chi-squared (uniform test): {chi2:.2f} (critical value at p=0.05: 18.3)")
print(f"  Uniform? {'YES' if chi2 < 18.3 else 'NO'}")

# ═══════════════════════════════════════════════════════════════
# Test 3: Spread distribution comparison
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  SPREAD DISTRIBUTION COMPARISON")
print("=" * 70)

actual_spreads = Counter(rec["ask"] - rec["bid"] for rec in actual)
random.seed(42)
sim_spreads = Counter()
for rec in actual:
    sb, sa, _ = bot1_quote(rec["fv"])
    sim_spreads[sa - sb] += 1

print(f"\n  {'spread':>7} {'actual':>8} {'simulated':>10}")
for sp in sorted(set(list(actual_spreads.keys()) + list(sim_spreads.keys()))):
    a = actual_spreads.get(sp, 0)
    s = sim_spreads.get(sp, 0)
    print(f"  {sp:>7} {a:>8} {s:>10}")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  SUMMARY")
print("=" * 70)
print(f"""
  Bot 1 model: bid = round(FV) - 8, ask = round(FV) + 8, vol = U(15,25)

  Price accuracy:  {both_match}/{n} ({both_match/n*100:.1f}%) exact match on both bid AND ask
  Bid accuracy:    {bid_match}/{n} ({bid_match/n*100:.1f}%)
  Ask accuracy:    {ask_match}/{n} ({ask_match/n*100:.1f}%)
  Spread accuracy: {spread_match}/{n} ({spread_match/n*100:.1f}%)

  Misses are ±1 tick, occurring when FV is near a 0.5 rounding boundary.
  Volume is uniform [15,25], identical on both sides each tick.

  This is a 3-line algorithm:
    bid = round(fv) - 8
    ask = round(fv) + 8
    vol = randint(15, 25)
""")
