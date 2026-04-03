"""
Nail down the exact Bot 1 quoting rule by examining the misses.

We know: bid ≈ round(FV) - 8, ask ≈ round(FV) + 8, matching 98.3%.
The 1.7% misses all have spread=16 instead of 15.
Hypothesis: bot uses TWO independent rounding operations:
  bid = some_round_down(FV) - 8
  ask = some_round_up(FV) + 8
And when FV is in a transition zone, they round differently.
"""

import json, math
from pathlib import Path
from collections import Counter

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]

# Extract Bot 1 (worst levels)
records = []
for r in rows:
    fv = r["fv"]
    worst_bid = min(r["bids"])
    worst_ask = max(r["asks"])
    bv = r["bid_vols"].get(str(worst_bid), r["bid_vols"].get(worst_bid, 0))
    av = r["ask_vols"].get(str(worst_ask), r["ask_vols"].get(worst_ask, 0))
    records.append({"fv": fv, "bid": worst_bid, "ask": worst_ask, "bv": bv, "av": av})

# ═══════════════════════════════════════════════════════════════
# For each record, compute: what value R makes bid = R - 8?
# i.e., R_bid = bid + 8. And R_ask = ask - 8.
# If the rule is bid = round(FV) - 8, then R_bid should = round(FV).
# ═══════════════════════════════════════════════════════════════
print("=" * 70)
print("  EXACT ROUNDING ANALYSIS")
print("  R_bid = bid + 8 (should be some rounding of FV)")
print("  R_ask = ask - 8 (should be some rounding of FV)")
print("=" * 70)

# Scatter: FV fractional part vs R_bid, R_ask
print(f"\n  FV frac → R_bid, R_ask (offset from floor(FV)):")
print(f"  {'fv_frac':>8} {'R_bid':>8} {'R_ask':>8} {'same?':>6}")

from collections import defaultdict
frac_data = defaultdict(lambda: {"r_bid": [], "r_ask": []})

for rec in records:
    fv = rec["fv"]
    r_bid = rec["bid"] + 8  # What value was "rounded" to get the bid
    r_ask = rec["ask"] - 8  # What value was "rounded" to get the ask
    frac = fv - math.floor(fv)
    frac_bin = round(frac * 20) / 20
    if frac_bin >= 1.0: frac_bin = 0.0

    # Store offset from floor(FV)
    frac_data[frac_bin]["r_bid"].append(r_bid - math.floor(fv))
    frac_data[frac_bin]["r_ask"].append(r_ask - math.floor(fv))

for f in sorted(frac_data):
    d = frac_data[f]
    rb = Counter(d["r_bid"])
    ra = Counter(d["r_ask"])
    rb_str = ", ".join(f"{v}:{c}" for v, c in sorted(rb.items()))
    ra_str = ", ".join(f"{v}:{c}" for v, c in sorted(ra.items()))
    print(f"  {f:>8.2f}  bid_R: {rb_str:<25}  ask_R: {ra_str}")

# ═══════════════════════════════════════════════════════════════
# Now let's look at the exact transition points
# When does R_bid flip from N to N+1? When does R_ask flip?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  TRANSITION POINTS: where does the rounding flip?")
print("=" * 70)

# For each consecutive pair, check if R_bid or R_ask changed
transitions_bid = []
transitions_ask = []

for i in range(len(records) - 1):
    fv = records[i]["fv"]
    fv_next = records[i+1]["fv"]
    rb = records[i]["bid"] + 8
    rb_next = records[i+1]["bid"] + 8
    ra = records[i]["ask"] - 8
    ra_next = records[i+1]["ask"] - 8

    if rb != rb_next:
        # R_bid changed — the FV crossed a rounding boundary
        transitions_bid.append({
            "fv_before": fv, "fv_after": fv_next,
            "rb_before": rb, "rb_after": rb_next,
            "frac_before": fv - math.floor(fv),
            "frac_after": fv_next - math.floor(fv_next),
        })

    if ra != ra_next:
        transitions_ask.append({
            "fv_before": fv, "fv_after": fv_next,
            "ra_before": ra, "ra_after": ra_next,
            "frac_before": fv - math.floor(fv),
            "frac_after": fv_next - math.floor(fv_next),
        })

# For UP transitions (R goes from N to N+1), what's the FV fractional part?
print(f"\n  BID rounding transitions ({len(transitions_bid)} total):")
up_fracs = [t["frac_after"] for t in transitions_bid if t["rb_after"] > t["rb_before"]]
down_fracs = [t["frac_before"] for t in transitions_bid if t["rb_after"] < t["rb_before"]]

if up_fracs:
    print(f"    UP (R_bid increases): FV_frac at transition")
    print(f"      mean={sum(up_fracs)/len(up_fracs):.4f}  min={min(up_fracs):.4f}  max={max(up_fracs):.4f}  n={len(up_fracs)}")
if down_fracs:
    print(f"    DOWN (R_bid decreases): FV_frac at transition")
    print(f"      mean={sum(down_fracs)/len(down_fracs):.4f}  min={min(down_fracs):.4f}  max={max(down_fracs):.4f}  n={len(down_fracs)}")

print(f"\n  ASK rounding transitions ({len(transitions_ask)} total):")
up_fracs_a = [t["frac_after"] for t in transitions_ask if t["ra_after"] > t["ra_before"]]
down_fracs_a = [t["frac_before"] for t in transitions_ask if t["ra_after"] < t["ra_before"]]

if up_fracs_a:
    print(f"    UP (R_ask increases): FV_frac at transition")
    print(f"      mean={sum(up_fracs_a)/len(up_fracs_a):.4f}  min={min(up_fracs_a):.4f}  max={max(up_fracs_a):.4f}  n={len(up_fracs_a)}")
if down_fracs_a:
    print(f"    DOWN (R_ask decreases): FV_frac at transition")
    print(f"      mean={sum(down_fracs_a)/len(down_fracs_a):.4f}  min={min(down_fracs_a):.4f}  max={max(down_fracs_a):.4f}  n={len(down_fracs_a)}")

# ═══════════════════════════════════════════════════════════════
# FINAL TEST: the simplest rule that gets 100%
# Maybe: bid = floor(FV + 0.5) - 8  (which IS round())
# but ties go a specific way, and sometimes there's a ±1 noise
# Let's just check: is the "miss" always exactly ±1 from round(FV)-8?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  MISS ANALYSIS: how far off is round(FV)-8 when it misses?")
print("=" * 70)

miss_deltas = Counter()
for rec in records:
    predicted = round(rec["fv"]) - 8
    delta = rec["bid"] - predicted
    if delta != 0:
        miss_deltas[delta] += 1

print(f"  BID misses (actual - predicted):")
for d in sorted(miss_deltas):
    print(f"    delta={d:>+2}: {miss_deltas[d]}")

miss_deltas_ask = Counter()
for rec in records:
    predicted = round(rec["fv"]) + 8
    delta = rec["ask"] - predicted
    if delta != 0:
        miss_deltas_ask[delta] += 1

print(f"\n  ASK misses (actual - predicted):")
for d in sorted(miss_deltas_ask):
    print(f"    delta={d:>+2}: {miss_deltas_ask[d]}")

# Check: when bid misses by -1, what's the FV frac?
print(f"\n  When bid = round(FV)-8-1 (bid is 1 lower than expected):")
for rec in records:
    if rec["bid"] == round(rec["fv"]) - 9:
        frac = rec["fv"] - math.floor(rec["fv"])
        print(f"    fv={rec['fv']:.4f} frac={frac:.4f} bid={rec['bid']} expected={round(rec['fv'])-8}")
        if sum(1 for r in records if r["bid"] == round(r["fv"])-9) > 15:
            break  # don't spam

print(f"\n  When ask = round(FV)+8+1 (ask is 1 higher than expected):")
count = 0
for rec in records:
    if rec["ask"] == round(rec["fv"]) + 9:
        frac = rec["fv"] - math.floor(rec["fv"])
        print(f"    fv={rec['fv']:.4f} frac={frac:.4f} ask={rec['ask']} expected={round(rec['fv'])+8}")
        count += 1
        if count > 15: break
