"""
Extract true FV and full order book from a hold-1-unit submission log.

Input:  ~/Downloads/{submission_id}/  containing {id}.json
Output: calibration/tomatoes/data/fv_and_book.json

Requires a submission where we buy exactly 1 TOMATO at t=0 and hold.
PnL(t) = -buy_price + 1 * server_fv(t), so server_fv = pnl + buy_price.
"""

import json, sys
from pathlib import Path

SUBMISSION_DIR = Path.home() / "Downloads" / "43285"
OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open(SUBMISSION_DIR / "43285.json") as f:
    data = json.load(f)

act_lines = data["activitiesLog"].strip().split("\n")

# Find the ask price at t=0 (our buy price)
for line in act_lines[1:]:
    cols = line.split(";")
    if len(cols) < 17 or cols[2] != "TOMATOES":
        continue
    if int(cols[1]) == 0:
        buy_price = int(cols[9])  # ask_price_1
        break

print(f"Buy price: {buy_price}")

rows = []
for line in act_lines[1:]:
    cols = line.split(";")
    if len(cols) < 17 or cols[2] != "TOMATOES":
        continue
    ts = int(cols[1])
    pnl = float(cols[16])

    bids = []
    bid_vols = []
    for i, vi in [(3, 4), (5, 6), (7, 8)]:
        if cols[i]:
            bids.append(int(cols[i]))
            bid_vols.append(int(cols[vi]))

    asks = []
    ask_vols = []
    for i, vi in [(9, 10), (11, 12), (13, 14)]:
        if cols[i]:
            asks.append(int(cols[i]))
            ask_vols.append(int(cols[vi]))

    fv = pnl + buy_price if ts > 0 else None

    rows.append({
        "ts": ts,
        "fv": fv,
        "bids": sorted(bids, reverse=True),
        "asks": sorted(asks),
        "bid_vols": dict(zip(bids, bid_vols)),
        "ask_vols": dict(zip(asks, ask_vols)),
        "mid_price": float(cols[15]),
    })

out = {"buy_price": buy_price, "rows": rows}
outpath = OUTPUT_DIR / "fv_and_book.json"
with open(outpath, "w") as f:
    json.dump(out, f)

print(f"Wrote {len(rows)} rows to {outpath}")
print(f"FV range: {min(r['fv'] for r in rows if r['fv']):.4f} to {max(r['fv'] for r in rows if r['fv']):.4f}")
