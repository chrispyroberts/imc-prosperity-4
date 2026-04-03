"""
Analyze Bot 1 (WALL bot) quoting behavior relative to true FV.

Bot 1 is the deepest level — always present, spread 15-16.
Goal: find the simplest deterministic rule that maps FV → (bid, ask, bid_vol, ask_vol).
"""

import json, math
from pathlib import Path
from collections import Counter

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]
print(f"Rows with FV: {len(rows)}")

# ═══════════════════════════════════════════════════════════════
# Extract Bot 1 quotes: the WORST (deepest) bid and ask
# Bot 1 is always the outermost level
# ═══════════════════════════════════════════════════════════════

records = []
for r in rows:
    fv = r["fv"]
    worst_bid = min(r["bids"])
    worst_ask = max(r["asks"])
    bid_vol = r["bid_vols"][str(worst_bid)] if str(worst_bid) in r["bid_vols"] else r["bid_vols"].get(worst_bid, 0)
    ask_vol = r["ask_vols"][str(worst_ask)] if str(worst_ask) in r["ask_vols"] else r["ask_vols"].get(worst_ask, 0)

    records.append({
        "fv": fv,
        "bid": worst_bid,
        "ask": worst_ask,
        "bid_vol": bid_vol,
        "ask_vol": ask_vol,
        "bid_off": worst_bid - fv,
        "ask_off": worst_ask - fv,
        "spread": worst_ask - worst_bid,
    })

# ═══════════════════════════════════════════════════════════════
# STEP 1: What integer relationship maps FV → bid?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  STEP 1: Reverse-engineer the bid formula")
print("=" * 70)

# Hypothesis: bid = floor(FV) - K  or  round(FV) - K  or  floor(FV - offset)
# Let's check various formulas

def test_formula(name, func):
    matches = 0
    misses = []
    for rec in records:
        predicted = func(rec["fv"])
        if predicted == rec["bid"]:
            matches += 1
        else:
            misses.append((rec["fv"], rec["bid"], predicted))
    pct = matches / len(records) * 100
    print(f"  {name:<40} {matches}/{len(records)} ({pct:.1f}%)")
    if misses and len(misses) <= 5:
        for fv, actual, pred in misses[:5]:
            print(f"    MISS: fv={fv:.4f} actual={actual} predicted={pred}")
    return matches, misses

# Try various formulas for BID
print("\n  BID formulas:")
test_formula("floor(FV) - 8", lambda fv: math.floor(fv) - 8)
test_formula("round(FV) - 8", lambda fv: round(fv) - 8)
test_formula("floor(FV - 0.5) - 7", lambda fv: math.floor(fv - 0.5) - 7)
test_formula("round(FV - 0.5) - 7", lambda fv: round(fv - 0.5) - 7)
test_formula("floor(FV + 0.5) - 8", lambda fv: math.floor(fv + 0.5) - 8)
test_formula("int(FV) - 8", lambda fv: int(fv) - 8)
test_formula("ceil(FV) - 8", lambda fv: math.ceil(fv) - 8)
test_formula("floor(FV) - 7", lambda fv: math.floor(fv) - 7)
test_formula("round(FV) - 7", lambda fv: round(fv) - 7)

# ═══════════════════════════════════════════════════════════════
# STEP 2: Same for ASK
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  STEP 2: Reverse-engineer the ask formula")
print("=" * 70)

def test_ask_formula(name, func):
    matches = 0
    misses = []
    for rec in records:
        predicted = func(rec["fv"])
        if predicted == rec["ask"]:
            matches += 1
        else:
            misses.append((rec["fv"], rec["ask"], predicted))
    pct = matches / len(records) * 100
    print(f"  {name:<40} {matches}/{len(records)} ({pct:.1f}%)")
    if misses and len(misses) <= 5:
        for fv, actual, pred in misses[:5]:
            print(f"    MISS: fv={fv:.4f} actual={actual} predicted={pred}")
    return matches, misses

print("\n  ASK formulas:")
test_ask_formula("ceil(FV) + 8", lambda fv: math.ceil(fv) + 8)
test_ask_formula("round(FV) + 8", lambda fv: round(fv) + 8)
test_ask_formula("ceil(FV + 0.5) + 7", lambda fv: math.ceil(fv + 0.5) + 7)
test_ask_formula("round(FV + 0.5) + 7", lambda fv: round(fv + 0.5) + 7)
test_ask_formula("floor(FV + 0.5) + 8", lambda fv: math.floor(fv + 0.5) + 8)
test_ask_formula("floor(FV) + 8", lambda fv: math.floor(fv) + 8)
test_ask_formula("ceil(FV) + 7", lambda fv: math.ceil(fv) + 7)
test_ask_formula("round(FV) + 7", lambda fv: round(fv) + 7)
test_ask_formula("floor(FV) + 9", lambda fv: math.floor(fv) + 9)

# ═══════════════════════════════════════════════════════════════
# STEP 3: Brute-force search for the formula
# Try: bid = floor/ceil/round(FV + shift) + offset for all combos
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  STEP 3: Brute-force formula search")
print("=" * 70)

best_bid_match = 0
best_bid_formula = ""
best_ask_match = 0
best_ask_formula = ""

for rnd_name, rnd_func in [("floor", math.floor), ("ceil", math.ceil), ("round", round)]:
    for shift in [x * 0.25 for x in range(-4, 5)]:
        for offset in range(-10, -5):
            matches = sum(1 for rec in records if rnd_func(rec["fv"] + shift) + offset == rec["bid"])
            if matches > best_bid_match:
                best_bid_match = matches
                best_bid_formula = f"bid = {rnd_name}(FV + {shift}) + {offset}"
        for offset in range(5, 11):
            matches = sum(1 for rec in records if rnd_func(rec["fv"] + shift) + offset == rec["ask"])
            if matches > best_ask_match:
                best_ask_match = matches
                best_ask_formula = f"ask = {rnd_name}(FV + {shift}) + {offset}"

print(f"  Best BID: {best_bid_formula}  → {best_bid_match}/{len(records)} ({best_bid_match/len(records)*100:.1f}%)")
print(f"  Best ASK: {best_ask_formula}  → {best_ask_match}/{len(records)} ({best_ask_match/len(records)*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
# STEP 4: Volume analysis
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  STEP 4: Volume distribution")
print("=" * 70)

bv = [rec["bid_vol"] for rec in records]
av = [rec["ask_vol"] for rec in records]

print(f"\n  Bid volumes: min={min(bv)} max={max(bv)} mean={sum(bv)/len(bv):.1f}")
print(f"  Ask volumes: min={min(av)} max={max(av)} mean={sum(av)/len(av):.1f}")

print(f"\n  Bid vol distribution:")
bvc = Counter(bv)
for v in sorted(bvc):
    print(f"    vol={v:>3}: {bvc[v]:>5} ({bvc[v]/len(bv)*100:.1f}%)")

print(f"\n  Ask vol distribution:")
avc = Counter(av)
for v in sorted(avc):
    print(f"    vol={v:>3}: {avc[v]:>5} ({avc[v]/len(av)*100:.1f}%)")

# Are bid and ask volumes correlated?
# Same tick: are they the same?
same_vol = sum(1 for rec in records if rec["bid_vol"] == rec["ask_vol"])
print(f"\n  Same bid/ask volume on same tick: {same_vol}/{len(records)} ({same_vol/len(records)*100:.1f}%)")

# Are volumes independent of FV?
from collections import defaultdict
vol_by_frac = defaultdict(list)
for rec in records:
    frac = round((rec["fv"] - math.floor(rec["fv"])) * 10) / 10
    vol_by_frac[frac].append(rec["bid_vol"])

print(f"\n  Bid volume vs FV fraction (checking independence):")
for f in sorted(vol_by_frac):
    vs = vol_by_frac[f]
    print(f"    frac={f:.1f}: mean_vol={sum(vs)/len(vs):.1f}  n={len(vs)}")

# ═══════════════════════════════════════════════════════════════
# STEP 5: Examine the misses from the best formula
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  STEP 5: Analyzing misses from best bid/ask formulas")
print("=" * 70)

# Re-run best formulas and show all misses
# Parse the best formulas
# For now just hardcode from the search results and show misses in detail
for rec in records:
    fv = rec["fv"]
    frac = fv - math.floor(fv)
    # Show cases where the bid/ask is far from typical
    bid_off = rec["bid_off"]
    ask_off = rec["ask_off"]
    if abs(bid_off) > 8.3 or abs(bid_off) < 7.1 or abs(ask_off) > 8.3 or abs(ask_off) < 7.1:
        print(f"  fv={fv:.4f} frac={frac:.4f} bid={rec['bid']} ({bid_off:+.3f}) ask={rec['ask']} ({ask_off:+.3f}) spread={rec['spread']}")
