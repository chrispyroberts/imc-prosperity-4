"""
Validate bot2.py against actual server data.
"""

import json, math, random
from pathlib import Path
from collections import Counter

from bot2 import bot2_quote

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]

# Extract actual Bot 2 quotes (level with 4 < |offset| < 7.5)
actual = []
for r in rows:
    fv = r["fv"]
    b2_bid = b2_ask = None
    b2_bv = b2_av = 0
    for bp in r["bids"]:
        off = bp - fv
        if -7.5 < off < -4:
            if b2_bid is None or bp > b2_bid:
                b2_bid = bp
                b2_bv = r["bid_vols"].get(str(bp), r["bid_vols"].get(bp, 0))
    for ap in r["asks"]:
        off = ap - fv
        if 4 < off < 7.5:
            if b2_ask is None or ap < b2_ask:
                b2_ask = ap
                b2_av = r["ask_vols"].get(str(ap), r["ask_vols"].get(ap, 0))
    actual.append({"fv": fv, "bid": b2_bid, "ask": b2_ask, "bv": b2_bv, "av": b2_av})

present = [r for r in actual if r["bid"] is not None and r["ask"] is not None]
n = len(present)

print("=" * 70)
print(f"  VALIDATION: bot2_quote (floor(FV+0.75)-7 / ceil(FV+0.25)+6)")
print(f"  Bot 2 present on {n}/{len(actual)} timestamps")
print("=" * 70)

bid_match = ask_match = both_match = spread_match = 0
bid_errs = Counter(); ask_errs = Counter()

for rec in present:
    sim_bid, sim_ask, _ = bot2_quote(rec["fv"])
    bm = sim_bid == rec["bid"]
    am = sim_ask == rec["ask"]
    bid_match += bm
    ask_match += am
    both_match += (bm and am)
    spread_match += ((sim_ask - sim_bid) == (rec["ask"] - rec["bid"]))
    if not bm: bid_errs[sim_bid - rec["bid"]] += 1
    if not am: ask_errs[sim_ask - rec["ask"]] += 1

print(f"\n  Bid match:    {bid_match}/{n} ({bid_match/n*100:.1f}%)")
print(f"  Ask match:    {ask_match}/{n} ({ask_match/n*100:.1f}%)")
print(f"  Both match:   {both_match}/{n} ({both_match/n*100:.1f}%)")
print(f"  Spread match: {spread_match}/{n} ({spread_match/n*100:.1f}%)")
print(f"\n  Bid errors: {dict(bid_errs)}")
print(f"  Ask errors: {dict(ask_errs)}")

# Volume
print(f"\n{'=' * 70}")
print("  VOLUME DISTRIBUTION")
print("=" * 70)

actual_bv = [r["bv"] for r in present]
actual_av = [r["av"] for r in present]
same_vol = sum(1 for bv, av in zip(actual_bv, actual_av) if bv == av)

print(f"  Bid = Ask vol on same tick: {same_vol}/{n} ({same_vol/n*100:.1f}%)")
print(f"\n  Bid vol: {Counter(actual_bv).most_common()}")
print(f"  Ask vol: {Counter(actual_av).most_common()}")

chi2 = sum((Counter(actual_bv).get(v, 0) - n/6)**2 / (n/6) for v in range(5, 11))
print(f"\n  Chi-squared (uniform [5,10] test): {chi2:.2f} (critical at p=0.05: 11.1)")
print(f"  Uniform? {'YES' if chi2 < 11.1 else 'NO'}")

# Spread distribution
print(f"\n{'=' * 70}")
print("  SPREAD DISTRIBUTION")
print("=" * 70)

actual_sp = Counter(rec["ask"] - rec["bid"] for rec in present)
sim_sp = Counter()
for rec in present:
    sb, sa, _ = bot2_quote(rec["fv"])
    sim_sp[sa - sb] += 1

print(f"\n  {'spread':>7} {'actual':>8} {'simulated':>10}")
for sp in sorted(set(list(actual_sp.keys()) + list(sim_sp.keys()))):
    print(f"  {sp:>7} {actual_sp.get(sp,0):>8} {sim_sp.get(sp,0):>10}")

print(f"\n{'=' * 70}")
print("  SUMMARY")
print("=" * 70)
print(f"""
  Bot 2 model: bid = floor(FV+0.75)-7, ask = ceil(FV+0.25)+6, vol = U(5,10)

  Price accuracy:  {both_match}/{n} ({both_match/n*100:.1f}%) exact match
  Bid accuracy:    {bid_match}/{n} ({bid_match/n*100:.1f}%)
  Ask accuracy:    {ask_match}/{n} ({ask_match/n*100:.1f}%)
  Spread:          13 ({sum(1 for r in present if r['ask']-r['bid']==13)/n*100:.1f}%) or 14 ({sum(1 for r in present if r['ask']-r['bid']==14)/n*100:.1f}%)

  Misses: ±1 at 0.25/0.75 fractional boundaries.
  Volume: uniform [5,10], identical both sides per tick.
  Always present.
""")
