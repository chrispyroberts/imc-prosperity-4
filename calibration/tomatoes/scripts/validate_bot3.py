"""
Validate bot3.py against actual server data.
Compares simulated Bot 3 behavior to real Bot 3 events on every dimension,
following the conditioning philosophy: check every variable | every other variable.
"""

import json, math, random
from pathlib import Path
from collections import Counter, defaultdict

from bot3 import bot3_quote

DATA = Path(__file__).parent.parent / "data" / "fv_and_book.json"
with open(DATA) as f:
    data = json.load(f)

rows = [r for r in data["rows"] if r["fv"] is not None]

# ═══════════════════════════════════════════════════════════════
# Extract actual Bot 3 events
# ═══════════════════════════════════════════════════════════════
actual_events = []
for r in rows:
    fv = r["fv"]
    for bp in r["bids"]:
        off = bp - fv
        if abs(off) <= 4:
            vol = r["bid_vols"].get(str(bp), r["bid_vols"].get(bp, 0))
            crossing = bp > fv
            actual_events.append({
                "side": "bid", "price": bp, "vol": vol, "fv": fv,
                "delta": bp - round(fv), "crossing": crossing,
            })
    for ap in r["asks"]:
        off = ap - fv
        if abs(off) <= 4:
            vol = r["ask_vols"].get(str(ap), r["ask_vols"].get(ap, 0))
            crossing = ap < fv
            actual_events.append({
                "side": "ask", "price": ap, "vol": vol, "fv": fv,
                "delta": ap - round(fv), "crossing": crossing,
            })

# ═══════════════════════════════════════════════════════════════
# Simulate Bot 3 over same FV stream, collect events
# ═══════════════════════════════════════════════════════════════
random.seed(42)
N_SIMS = 50  # run 50x over the same FV stream to get good stats

sim_events = []
sim_presence_counts = []
for _ in range(N_SIMS):
    count = 0
    for r in rows:
        result = bot3_quote(r["fv"])
        if result is not None:
            side, price, vol = result
            fv = r["fv"]
            crossing = (side == "bid" and price > fv) or (side == "ask" and price < fv)
            sim_events.append({
                "side": side, "price": price, "vol": vol, "fv": fv,
                "delta": price - round(fv), "crossing": crossing,
            })
            count += 1
    sim_presence_counts.append(count)

n_actual = len(actual_events)
n_sim = len(sim_events)
n_rows = len(rows)

print("=" * 70)
print("  BOT 3 VALIDATION")
print("=" * 70)

# ═══════════════════════════════════════════════════════════════
# 1. Presence rate
# ═══════════════════════════════════════════════════════════════
print(f"\n  PRESENCE RATE:")
actual_rate = n_actual / n_rows * 100
sim_rate_mean = sum(sim_presence_counts) / len(sim_presence_counts) / n_rows * 100
print(f"    Actual:    {n_actual}/{n_rows} ({actual_rate:.1f}%)")
print(f"    Simulated: {sum(sim_presence_counts)/N_SIMS:.0f}/{n_rows} ({sim_rate_mean:.1f}%) [mean over {N_SIMS} runs]")

# ═══════════════════════════════════════════════════════════════
# 2. Side distribution
# ═══════════════════════════════════════════════════════════════
print(f"\n  SIDE DISTRIBUTION:")
a_sides = Counter(e["side"] for e in actual_events)
s_sides = Counter(e["side"] for e in sim_events)
for side in ["bid", "ask"]:
    a_pct = a_sides[side] / n_actual * 100
    s_pct = s_sides[side] / n_sim * 100
    print(f"    {side}: actual={a_pct:.1f}%  sim={s_pct:.1f}%")

# ═══════════════════════════════════════════════════════════════
# 3. Price offset distribution (delta = price - round(FV))
# ═══════════════════════════════════════════════════════════════
print(f"\n  PRICE OFFSET (price - round(FV)):")
a_deltas = Counter(e["delta"] for e in actual_events)
s_deltas = Counter(e["delta"] for e in sim_events)
print(f"    {'delta':>6} {'actual':>8} {'sim':>8}")
for d in sorted(set(list(a_deltas.keys()) + list(s_deltas.keys()))):
    a_pct = a_deltas.get(d, 0) / n_actual * 100
    s_pct = s_deltas.get(d, 0) / n_sim * 100
    print(f"    {d:>+6} {a_pct:>7.1f}% {s_pct:>7.1f}%")

# ═══════════════════════════════════════════════════════════════
# 4. Crossing rate
# ═══════════════════════════════════════════════════════════════
print(f"\n  CROSSING RATE (order on wrong side of FV):")
a_cross = sum(1 for e in actual_events if e["crossing"])
s_cross = sum(1 for e in sim_events if e["crossing"])
print(f"    Actual:    {a_cross}/{n_actual} ({a_cross/n_actual*100:.1f}%)")
print(f"    Simulated: {s_cross}/{n_sim} ({s_cross/n_sim*100:.1f}%)")

# ═══════════════════════════════════════════════════════════════
# 5. Volume | crossing (the key conditioned check)
# ═══════════════════════════════════════════════════════════════
print(f"\n  VOLUME | CROSSING:")
for label, events, n in [("Actual", actual_events, n_actual), ("Sim", sim_events, n_sim)]:
    cross_vols = [e["vol"] for e in events if e["crossing"]]
    pass_vols = [e["vol"] for e in events if not e["crossing"]]
    print(f"    {label}:")
    if cross_vols:
        print(f"      Crossing: n={len(cross_vols)} mean={sum(cross_vols)/len(cross_vols):.1f} range=[{min(cross_vols)},{max(cross_vols)}]")
    if pass_vols:
        print(f"      Passive:  n={len(pass_vols)} mean={sum(pass_vols)/len(pass_vols):.1f} range=[{min(pass_vols)},{max(pass_vols)}]")

# ═══════════════════════════════════════════════════════════════
# 6. Volume | delta (finer conditioning)
# ═══════════════════════════════════════════════════════════════
print(f"\n  VOLUME | DELTA (price offset from round(FV)):")
print(f"    {'delta':>6}  {'actual_mean':>11} {'actual_n':>8}  {'sim_mean':>11} {'sim_n':>8}")
a_vol_by_d = defaultdict(list)
s_vol_by_d = defaultdict(list)
for e in actual_events: a_vol_by_d[e["delta"]].append(e["vol"])
for e in sim_events: s_vol_by_d[e["delta"]].append(e["vol"])

for d in sorted(set(list(a_vol_by_d.keys()) + list(s_vol_by_d.keys()))):
    av = a_vol_by_d.get(d, [])
    sv = s_vol_by_d.get(d, [])
    a_mean = sum(av)/len(av) if av else 0
    s_mean = sum(sv)/len(sv) if sv else 0
    print(f"    {d:>+6}  {a_mean:>11.1f} {len(av):>8}  {s_mean:>11.1f} {len(sv):>8}")

# ═══════════════════════════════════════════════════════════════
# 7. Volume | (side, delta) (finest conditioning)
# ═══════════════════════════════════════════════════════════════
print(f"\n  VOLUME | (SIDE, DELTA):")
a_vol_by_sd = defaultdict(list)
s_vol_by_sd = defaultdict(list)
for e in actual_events: a_vol_by_sd[(e["side"], e["delta"])].append(e["vol"])
for e in sim_events: s_vol_by_sd[(e["side"], e["delta"])].append(e["vol"])

print(f"    {'(side,delta)':<15} {'actual_mean':>11} {'actual_n':>8}  {'sim_mean':>11} {'sim_n':>8}")
for key in sorted(set(list(a_vol_by_sd.keys()) + list(s_vol_by_sd.keys()))):
    av = a_vol_by_sd.get(key, [])
    sv = s_vol_by_sd.get(key, [])
    a_mean = sum(av)/len(av) if av else 0
    s_mean = sum(sv)/len(sv) if sv else 0
    print(f"    {str(key):<15} {a_mean:>11.1f} {len(av):>8}  {s_mean:>11.1f} {len(sv):>8}")

# ═══════════════════════════════════════════════════════════════
# 8. Volume distribution comparison (marginal, for completeness)
# ═══════════════════════════════════════════════════════════════
print(f"\n  VOLUME DISTRIBUTION (marginal):")
a_vc = Counter(e["vol"] for e in actual_events)
s_vc = Counter(e["vol"] for e in sim_events)
all_vols = sorted(set(list(a_vc.keys()) + list(s_vc.keys())))
print(f"    {'vol':>4} {'actual':>8} {'sim':>8}")
for v in all_vols:
    a_pct = a_vc.get(v, 0) / n_actual * 100
    s_pct = s_vc.get(v, 0) / n_sim * 100
    print(f"    {v:>4} {a_pct:>7.1f}% {s_pct:>7.1f}%")

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f"\n{'=' * 70}")
print("  SUMMARY")
print("=" * 70)
print(f"""
  Bot 3 model:
    Appear with p=0.063 per tick
    side = bid (46%) or ask (54%)
    price = round(FV) + choice([-2,-1,0,+1])
    vol = U(5,12) if crossing, U(2,6) if passive

  Presence rate:     actual {actual_rate:.1f}%  vs sim {sim_rate_mean:.1f}%
  Side split:        actual {a_sides['bid']/n_actual*100:.0f}/{a_sides['ask']/n_actual*100:.0f}  vs sim {s_sides['bid']/n_sim*100:.0f}/{s_sides['ask']/n_sim*100:.0f}
  Crossing rate:     actual {a_cross/n_actual*100:.1f}%  vs sim {s_cross/n_sim*100:.1f}%
  Crossing vol mean: actual {sum(e['vol'] for e in actual_events if e['crossing'])/max(a_cross,1):.1f}  vs sim {sum(e['vol'] for e in sim_events if e['crossing'])/max(s_cross,1):.1f}
  Passive vol mean:  actual {sum(e['vol'] for e in actual_events if not e['crossing'])/max(n_actual-a_cross,1):.1f}  vs sim {sum(e['vol'] for e in sim_events if not e['crossing'])/max(n_sim-s_cross,1):.1f}
""")
