"""
Monte Carlo order book simulator for TOMATOES.

Generates synthetic price/trade CSV files matching the Prosperity backtester format,
using the calibrated bot models (Bot 1, Bot 2, Bot 3) and a pure RW fair value.

Calibrated from server submission 43285 (hold-1-unit experiment).

FV model:  FV(t+1) = FV(t) + 0.496 * N(0,1), quantized to 1/2048
Bot 1:     bid = round(FV) - 8, ask = round(FV) + 8, vol = U(15,25) same both sides
Bot 2:     bid = floor(FV+0.75) - 7, ask = ceil(FV+0.25) + 6, vol = U(5,10) same both sides
Bot 3:     6.3% per tick, single-sided, price = round(FV) + choice(-2,-1,0,+1)
           vol depends on crossing: U(5,12) if crossing FV, U(2,6) if passive

Usage:
    python simulate_book.py [--sessions 100] [--seed 42] [--out-dir ../../data/mc_sessions]
"""

import argparse
import csv
import math
import os
import random
from pathlib import Path


FV_SIGMA = 0.496
FV_QUANT = 1.0 / 2048
N_STEPS = 2000       # server evaluation length (tutorial round)
FV_START = 5000.0


def quantize_fv(fv):
    """Quantize to nearest 1/2048."""
    return round(fv / FV_QUANT) * FV_QUANT


def generate_fv_path(n_steps, fv_start, sigma, rng):
    """Generate a pure random walk FV path."""
    fv = fv_start
    path = []
    for _ in range(n_steps):
        path.append(quantize_fv(fv))
        fv += sigma * rng.gauss(0, 1)
    return path


def bot1_quote(fv, rng):
    """Wall bot: round(FV) ± 8, vol U(15,25)."""
    r = round(fv)
    vol = rng.randint(15, 25)
    return r - 8, r + 8, vol, vol


def bot2_quote(fv, rng):
    """Inner bot: floor(FV+0.75)-7 / ceil(FV+0.25)+6, vol U(5,10)."""
    bid = math.floor(fv + 0.75) - 7
    ask = math.ceil(fv + 0.25) + 6
    vol = rng.randint(5, 10)
    return bid, ask, vol, vol


def bot3_quote(fv, rng):
    """Near-FV bot: 6.3% chance, single-sided, price = round(FV) + choice(-2,-1,0,+1)."""
    if rng.random() > 0.063:
        return None

    side = "bid" if rng.random() < 0.50 else "ask"
    price = round(fv) + rng.choice([-2, -1, 0, 1])

    if (side == "bid" and price > fv) or (side == "ask" and price < fv):
        vol = rng.randint(5, 12)
    else:
        vol = rng.randint(2, 6)

    return side, price, vol


def build_book(fv, rng):
    """Build order book from all 3 bots. Returns sorted bids (desc) and asks (asc)."""
    bids = {}  # price -> volume
    asks = {}

    # Bot 1
    b1_bid, b1_ask, b1_bv, b1_av = bot1_quote(fv, rng)
    bids[b1_bid] = b1_bv
    asks[b1_ask] = b1_av

    # Bot 2
    b2_bid, b2_ask, b2_bv, b2_av = bot2_quote(fv, rng)
    bids[b2_bid] = bids.get(b2_bid, 0) + b2_bv
    asks[b2_ask] = asks.get(b2_ask, 0) + b2_av

    # Bot 3
    b3 = bot3_quote(fv, rng)
    if b3 is not None:
        side, price, vol = b3
        if side == "bid":
            bids[price] = bids.get(price, 0) + vol
        else:
            asks[price] = asks.get(price, 0) + vol

    # Sort: bids descending, asks ascending, take top 3
    sorted_bids = sorted(bids.items(), key=lambda x: -x[0])[:3]
    sorted_asks = sorted(asks.items(), key=lambda x: x[0])[:3]

    return sorted_bids, sorted_asks


def generate_trade(fv, best_bid, best_ask, rng):
    """
    Generate a market trade with ~4% probability per step.

    Calibrated from real data:
    - 4% of timestamps have a trade
    - Price at best_bid or best_ask (~50/50 buy vs sell)
    - Quantity: uniform {2, 3, 4, 5}
    - Rare trades (~3% of trades) happen near FV (Bot 3 interactions)
    """
    if rng.random() > 0.04:
        return None

    qty = rng.randint(2, 5)

    # ~3% of trades are near-FV (Bot 3), rest are at best bid/ask
    if rng.random() < 0.03:
        # Near-FV trade
        price = round(fv) + rng.choice([-3, -2, 2, 3])
    else:
        # Trade at best bid or best ask (~50/50)
        if rng.random() < 0.5:
            price = best_bid   # sell trade (at bid)
        else:
            price = best_ask   # buy trade (at ask)

    return price, qty


def generate_session(session_id, fv_start, seed, out_dir, n_steps=N_STEPS):
    """Generate one session of price + trade data."""
    rng = random.Random(seed)
    fv_path = generate_fv_path(n_steps, fv_start, FV_SIGMA, rng)

    # Build price rows and trades
    price_rows = []
    trade_rows = []

    for t in range(n_steps):
        fv = fv_path[t]
        timestamp = t * 100
        sorted_bids, sorted_asks = build_book(fv, rng)

        # Pad to 3 levels
        bid_prices = [str(b[0]) for b in sorted_bids] + [""] * (3 - len(sorted_bids))
        bid_vols = [str(b[1]) for b in sorted_bids] + [""] * (3 - len(sorted_bids))
        ask_prices = [str(a[0]) for a in sorted_asks] + [""] * (3 - len(sorted_asks))
        ask_vols = [str(a[1]) for a in sorted_asks] + [""] * (3 - len(sorted_asks))

        best_bid = sorted_bids[0][0]
        best_ask = sorted_asks[0][0]
        mid_price = (best_bid + best_ask) / 2

        price_rows.append([
            -2, timestamp, "TOMATOES",
            bid_prices[0], bid_vols[0],
            bid_prices[1], bid_vols[1],
            bid_prices[2], bid_vols[2],
            ask_prices[0], ask_vols[0],
            ask_prices[1], ask_vols[1],
            ask_prices[2], ask_vols[2],
            mid_price, 0.0,
        ])

        # Generate market trade
        trade = generate_trade(fv, best_bid, best_ask, rng)
        if trade is not None:
            price, qty = trade
            trade_rows.append([timestamp, "", "", "TOMATOES", "TOMATOES", int(price), qty])

    # Write prices CSV
    session_dir = Path(out_dir) / f"session_{session_id:05d}" / "round0"
    session_dir.mkdir(parents=True, exist_ok=True)

    prices_path = session_dir / "prices_round_0_day_-2.csv"
    with open(prices_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "day", "timestamp", "product",
            "bid_price_1", "bid_volume_1",
            "bid_price_2", "bid_volume_2",
            "bid_price_3", "bid_volume_3",
            "ask_price_1", "ask_volume_1",
            "ask_price_2", "ask_volume_2",
            "ask_price_3", "ask_volume_3",
            "mid_price", "profit_and_loss",
        ])
        writer.writerows(price_rows)

    # Write trades CSV
    trades_path = session_dir / "trades_round_0_day_-2.csv"
    with open(trades_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["timestamp", "buyer", "seller", "symbol", "currency", "price", "quantity"])
        writer.writerows(trade_rows)

    return prices_path


def main():
    parser = argparse.ArgumentParser(description="TOMATOES MC book simulator")
    parser.add_argument("--sessions", type=int, default=10, help="Number of sessions")
    parser.add_argument("--steps", type=int, default=N_STEPS, help="Steps per session (server=2000, training=10000)")
    parser.add_argument("--seed", type=int, default=42, help="Base RNG seed")
    parser.add_argument("--fv-start", type=float, default=FV_START, help="Starting FV")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    if args.out_dir is None:
        args.out_dir = str(Path(__file__).parent.parent / "mc_sessions")

    print(f"Generating {args.sessions} sessions...")
    print(f"  FV: RW σ={FV_SIGMA}, start={args.fv_start}, quantized to 1/2048")
    print(f"  Steps: {args.steps} per session")
    print(f"  Bot 1: round(FV)±8, vol U(15,25)")
    print(f"  Bot 2: floor(FV+0.75)-7 / ceil(FV+0.25)+6, vol U(5,10)")
    print(f"  Bot 3: 6.3%, round(FV)+choice(-2..+1), vol depends on crossing")
    print(f"  Output: {args.out_dir}")

    for i in range(args.sessions):
        seed = args.seed + i
        path = generate_session(i, args.fv_start, seed, args.out_dir, args.steps)
        if i < 3 or i == args.sessions - 1:
            print(f"  Session {i}: {path}")
        elif i == 3:
            print(f"  ...")

    print(f"Done. {args.sessions} sessions in {args.out_dir}")


if __name__ == "__main__":
    main()
