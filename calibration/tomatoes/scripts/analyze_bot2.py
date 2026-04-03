"""
Analyze Bot 2 (INNER bot) quoting behavior relative to true FV.

Bot 2 is the second level — present ~54% of the time, spread ~13.
"""

import json, math
from pathlib import Path
from collections import Counter, defaultdict

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]

# ═══════════════════════════════════════════════════════════════
# Extract Bot 2: levels with 4 < |offset| ≤ 7
# Bot 1 is |offset| > 7, Bot 3 is |offset| ≤ 4
# ═══════════════════════════════════════════════════════════════

records = []
for r in rows:
    fv = r["fv"]
    b2_bids = []
    b2_asks = []

    for bp in r["bids"]:
        off = bp - fv
        if -7.5 < off < -4:
            vol = r["bid_vols"].get(str(bp), r["bid_vols"].get(bp, 0))
            b2_bids.append((bp, vol, off))

    for ap in r["asks"]:
        off = ap - fv
        if 4 < off < 7.5:
            vol = r["ask_vols"].get(str(ap), r["ask_vols"].get(ap, 0))
            b2_asks.append((ap, vol, off))

    records.append({
        "fv": fv,
        "ts": r["ts"],
        "b2_bids": b2_bids,
        "b2_asks": b2_asks,
        "present": len(b2_bids) > 0 and len(b2_asks) > 0,
        "bid_only": len(b2_bids) > 0 and len(b2_asks) == 0,
        "ask_only": len(b2_bids) == 0 and len(b2_asks) > 0,
    })

present = sum(1 for r in records if r["present"])
bid_only = sum(1 for r in records if r["bid_only"])
ask_only = sum(1 for r in records if r["ask_only"])
absent = sum(1 for r in records if not r["present"] and not r["bid_only"] and not r["ask_only"])

print("=" * 70)
print("  BOT 2 PRESENCE")
print("=" * 70)
print(f"  Both sides:  {present}/{len(records)} ({present/len(records)*100:.1f}%)")
print(f"  Bid only:    {bid_only}/{len(records)} ({bid_only/len(records)*100:.1f}%)")
print(f"  Ask only:    {ask_only}/{len(records)} ({ask_only/len(records)*100:.1f}%)")
print(f"  Absent:      {absent}/{len(records)} ({absent/len(records)*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
# When present, what are the offsets?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  BOT 2 OFFSETS (when both sides present)")
print("=" * 70)

bid_offs = []
ask_offs = []
bid_vols = []
ask_vols = []
spreads = []

for r in records:
    if not r["present"]:
        continue
    # Take the best (closest to FV) Bot 2 level on each side
    best_b2_bid = max(r["b2_bids"], key=lambda x: x[0])
    best_b2_ask = min(r["b2_asks"], key=lambda x: x[0])
    bid_offs.append(best_b2_bid[2])
    ask_offs.append(best_b2_ask[2])
    bid_vols.append(best_b2_bid[1])
    ask_vols.append(best_b2_ask[1])
    spreads.append(best_b2_ask[0] - best_b2_bid[0])

m_bo = sum(bid_offs)/len(bid_offs)
m_ao = sum(ask_offs)/len(ask_offs)
print(f"\n  Bid offset: mean={m_bo:+.4f}  min={min(bid_offs):+.4f}  max={max(bid_offs):+.4f}")
print(f"  Ask offset: mean={m_ao:+.4f}  min={min(ask_offs):+.4f}  max={max(ask_offs):+.4f}")

print(f"\n  Bid offset distribution (binned to 0.25):")
bc = Counter(round(x*4)/4 for x in bid_offs)
for v in sorted(bc):
    pct = bc[v]/len(bid_offs)*100
    bar = '#' * int(pct)
    print(f"    {v:>+6.2f}: {bc[v]:>5} ({pct:>5.1f}%) {bar}")

print(f"\n  Ask offset distribution (binned to 0.25):")
ac = Counter(round(x*4)/4 for x in ask_offs)
for v in sorted(ac):
    pct = ac[v]/len(ask_offs)*100
    bar = '#' * int(pct)
    print(f"    {v:>+6.2f}: {ac[v]:>5} ({pct:>5.1f}%) {bar}")

print(f"\n  Spread distribution:")
sc = Counter(spreads)
for v in sorted(sc):
    print(f"    {v}: {sc[v]}")

# ═══════════════════════════════════════════════════════════════
# Volume analysis
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  BOT 2 VOLUMES")
print("=" * 70)

print(f"\n  Bid volumes: min={min(bid_vols)} max={max(bid_vols)} mean={sum(bid_vols)/len(bid_vols):.1f}")
print(f"  Ask volumes: min={min(ask_vols)} max={max(ask_vols)} mean={sum(ask_vols)/len(ask_vols):.1f}")

bvc = Counter(bid_vols)
print(f"\n  Bid vol distribution:")
for v in sorted(bvc):
    print(f"    vol={v:>3}: {bvc[v]:>5} ({bvc[v]/len(bid_vols)*100:.1f}%)")

avc = Counter(ask_vols)
print(f"\n  Ask vol distribution:")
for v in sorted(avc):
    print(f"    vol={v:>3}: {avc[v]:>5} ({avc[v]/len(ask_vols)*100:.1f}%)")

same_vol = sum(1 for bv, av in zip(bid_vols, ask_vols) if bv == av)
print(f"\n  Same bid/ask vol: {same_vol}/{len(bid_vols)} ({same_vol/len(bid_vols)*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
# Presence vs FV fractional part
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  BOT 2 PRESENCE vs FV FRACTIONAL PART")
print("=" * 70)

frac_present = defaultdict(lambda: {"present": 0, "total": 0})
for r in records:
    frac = round((r["fv"] - math.floor(r["fv"])) * 20) / 20
    if frac >= 1.0: frac = 0.0
    frac_present[frac]["total"] += 1
    if r["present"]:
        frac_present[frac]["present"] += 1

print(f"\n  {'frac':>6} {'present':>8} {'total':>6} {'pct':>7}")
for f in sorted(frac_present):
    d = frac_present[f]
    print(f"  {f:>6.2f} {d['present']:>8} {d['total']:>6} {d['present']/d['total']*100:>6.1f}%")

# ═══════════════════════════════════════════════════════════════
# Brute-force formula search (same as bot1)
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  BRUTE-FORCE FORMULA SEARCH (when present)")
print("=" * 70)

# Extract actual bid/ask when present
present_recs = []
for r in records:
    if r["present"]:
        best_bid = max(r["b2_bids"], key=lambda x: x[0])
        best_ask = min(r["b2_asks"], key=lambda x: x[0])
        present_recs.append({"fv": r["fv"], "bid": best_bid[0], "ask": best_ask[0],
                              "bv": best_bid[1], "av": best_ask[1]})

n = len(present_recs)

best_bid_match = 0; best_bid_formula = ""
best_ask_match = 0; best_ask_formula = ""

for rnd_name, rnd_func in [("floor", math.floor), ("ceil", math.ceil), ("round", round)]:
    for shift in [x * 0.25 for x in range(-4, 5)]:
        for offset in range(-8, -4):
            matches = sum(1 for rec in present_recs if rnd_func(rec["fv"] + shift) + offset == rec["bid"])
            if matches > best_bid_match:
                best_bid_match = matches
                best_bid_formula = f"bid = {rnd_name}(FV + {shift}) + {offset}"
        for offset in range(4, 9):
            matches = sum(1 for rec in present_recs if rnd_func(rec["fv"] + shift) + offset == rec["ask"])
            if matches > best_ask_match:
                best_ask_match = matches
                best_ask_formula = f"ask = {rnd_name}(FV + {shift}) + {offset}"

print(f"  Best BID: {best_bid_formula}  → {best_bid_match}/{n} ({best_bid_match/n*100:.1f}%)")
print(f"  Best ASK: {best_ask_formula}  → {best_ask_match}/{n} ({best_ask_match/n*100:.1f}%)")

# Also check the exact R values (R_bid = bid + K)
print(f"\n  R_bid = bid + 7 offset from floor(FV):")
frac_rbid = defaultdict(list)
for rec in present_recs:
    r_bid = rec["bid"] + 7
    frac = round((rec["fv"] - math.floor(rec["fv"])) * 20) / 20
    frac_rbid[frac].append(r_bid - math.floor(rec["fv"]))

for f in sorted(frac_rbid):
    c = Counter(frac_rbid[f])
    print(f"    frac={f:.2f}: {dict(sorted(c.items()))}")

print(f"\n  R_ask = ask - 7 offset from floor(FV):")
frac_rask = defaultdict(list)
for rec in present_recs:
    r_ask = rec["ask"] - 7
    frac = round((rec["fv"] - math.floor(rec["fv"])) * 20) / 20
    frac_rask[frac].append(r_ask - math.floor(rec["fv"]))

for f in sorted(frac_rask):
    c = Counter(frac_rask[f])
    print(f"    frac={f:.2f}: {dict(sorted(c.items()))}")

# Miss analysis
print(f"\n  MISS ANALYSIS for best formula:")
bid_misses = Counter()
ask_misses = Counter()
for rec in present_recs:
    # Try round(FV) - 7 for bid
    pred_bid = round(rec["fv"]) - 7
    if pred_bid != rec["bid"]:
        bid_misses[rec["bid"] - pred_bid] += 1
    pred_ask = round(rec["fv"]) + 7
    if pred_ask != rec["ask"]:
        ask_misses[rec["ask"] - pred_ask] += 1

print(f"  round(FV)-7 bid misses: {dict(bid_misses)}  ({sum(bid_misses.values())} total)")
print(f"  round(FV)+7 ask misses: {dict(ask_misses)}  ({sum(ask_misses.values())} total)")

# Try other offsets
for off in [6, 7, 8]:
    bm = sum(1 for r in present_recs if round(r["fv"]) - off == r["bid"])
    am = sum(1 for r in present_recs if round(r["fv"]) + off == r["ask"])
    print(f"  round(FV)±{off}: bid={bm}/{n} ({bm/n*100:.1f}%)  ask={am}/{n} ({am/n*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
# Presence pattern: is it random or correlated with something?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  BOT 2 PRESENCE PATTERN")
print("=" * 70)

# Run length analysis: how long does Bot 2 stay present/absent?
present_runs = []
absent_runs = []
current_state = records[0]["present"]
run_len = 1
for i in range(1, len(records)):
    if records[i]["present"] == current_state:
        run_len += 1
    else:
        if current_state:
            present_runs.append(run_len)
        else:
            absent_runs.append(run_len)
        current_state = records[i]["present"]
        run_len = 1

if current_state:
    present_runs.append(run_len)
else:
    absent_runs.append(run_len)

print(f"\n  Present runs: n={len(present_runs)}  mean={sum(present_runs)/len(present_runs):.1f}  min={min(present_runs)}  max={max(present_runs)}")
print(f"  Absent runs:  n={len(absent_runs)}  mean={sum(absent_runs)/len(absent_runs):.1f}  min={min(absent_runs)}  max={max(absent_runs)}")

print(f"\n  Present run distribution:")
prc = Counter(present_runs)
for v in sorted(prc)[:15]:
    print(f"    len={v:>3}: {prc[v]:>4}")

print(f"\n  Absent run distribution:")
arc = Counter(absent_runs)
for v in sorted(arc)[:15]:
    print(f"    len={v:>3}: {arc[v]:>4}")
