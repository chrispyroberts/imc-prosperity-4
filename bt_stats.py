"""
Backtest fill analytics — wraps the backtester to track maker vs taker fills.

Usage (from prosperity4/):
    python bt_stats.py trader_v3.py 0 [--data data] [--no-out] [--match-trades all]

Passes all arguments through to the backtester, then prints a fill breakdown.
No changes to your trader or the backtester source required.
"""

import sys
from collections import defaultdict
from pathlib import Path

# ── Bootstrap: add backtester to path ──────────────────────────────
bt_dir = Path(__file__).parent / "backtester"
sys.path.insert(0, str(bt_dir))

from prosperity3bt import runner
from prosperity3bt.datamodel import Order, Symbol, Trade, TradingState
from prosperity3bt.models import BacktestResult, MarketTrade, TradeMatchingMode, TradeRow

# ── Stats accumulator ──────────────────────────────────────────────

stats = defaultdict(lambda: {
    "maker_buys": 0, "maker_sells": 0,
    "taker_buys": 0, "taker_sells": 0,
    "maker_buy_vol": 0, "maker_sell_vol": 0,
    "taker_buy_vol": 0, "taker_sell_vol": 0,
    "maker_buy_cost": 0, "maker_sell_cost": 0,
    "taker_buy_cost": 0, "taker_sell_cost": 0,
    "steps_with_fills": 0,
    "total_steps": 0,
    "orders_submitted": 0,
    "orders_unfilled": 0,
})


# ── Patched matching functions ─────────────────────────────────────

_orig_match_buy = runner.match_buy_order
_orig_match_sell = runner.match_sell_order
_orig_match_orders = runner.match_orders


def _tagged_match_buy(state, data, order, market_trades, mode):
    """Wrapper that tags fills as maker (book) vs taker (market trade)."""
    product = order.symbol
    qty_before = order.quantity

    # --- Phase 1: maker fills (against order book) ---
    order_depth = state.order_depths[product]
    price_matches = sorted(p for p in order_depth.sell_orders if p <= order.price)

    trades = []
    for price in price_matches:
        volume = min(order.quantity, abs(order_depth.sell_orders[price]))
        trades.append(Trade(order.symbol, price, volume, "SUBMISSION", "", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= price * volume

        order_depth.sell_orders[price] += volume
        if order_depth.sell_orders[price] == 0:
            order_depth.sell_orders.pop(price)

        order.quantity -= volume

        s = stats[product]
        s["maker_buys"] += 1
        s["maker_buy_vol"] += volume
        s["maker_buy_cost"] += price * volume

        if order.quantity == 0:
            return trades

    # --- Phase 2: taker fills (against market trades) ---
    if mode == TradeMatchingMode.none:
        return trades

    for mt in market_trades:
        if (mt.sell_quantity == 0
            or mt.trade.price > order.price
            or (mt.trade.price == order.price and mode == TradeMatchingMode.worse)):
            continue

        volume = min(order.quantity, mt.sell_quantity)
        trades.append(Trade(order.symbol, order.price, volume, "SUBMISSION", mt.trade.seller, state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= order.price * volume
        mt.sell_quantity -= volume
        order.quantity -= volume

        s = stats[product]
        s["taker_buys"] += 1
        s["taker_buy_vol"] += volume
        s["taker_buy_cost"] += order.price * volume

        if order.quantity == 0:
            return trades

    return trades


def _tagged_match_sell(state, data, order, market_trades, mode):
    """Wrapper that tags fills as maker (book) vs taker (market trade)."""
    product = order.symbol
    qty_before = abs(order.quantity)

    order_depth = state.order_depths[product]
    price_matches = sorted((p for p in order_depth.buy_orders if p >= order.price), reverse=True)

    trades = []
    for price in price_matches:
        volume = min(abs(order.quantity), order_depth.buy_orders[price])
        trades.append(Trade(order.symbol, price, volume, "", "SUBMISSION", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += price * volume

        order_depth.buy_orders[price] -= volume
        if order_depth.buy_orders[price] == 0:
            order_depth.buy_orders.pop(price)

        order.quantity += volume

        s = stats[product]
        s["maker_sells"] += 1
        s["maker_sell_vol"] += volume
        s["maker_sell_cost"] += price * volume

        if order.quantity == 0:
            return trades

    if mode == TradeMatchingMode.none:
        return trades

    for mt in market_trades:
        if (mt.buy_quantity == 0
            or mt.trade.price < order.price
            or (mt.trade.price == order.price and mode == TradeMatchingMode.worse)):
            continue

        volume = min(abs(order.quantity), mt.buy_quantity)
        trades.append(Trade(order.symbol, order.price, volume, mt.trade.buyer, "SUBMISSION", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += order.price * volume
        mt.buy_quantity -= volume
        order.quantity += volume

        s = stats[product]
        s["taker_sells"] += 1
        s["taker_sell_vol"] += volume
        s["taker_sell_cost"] += order.price * volume

        if order.quantity == 0:
            return trades

    return trades


def _tagged_match_orders(state, data, orders, result, mode):
    """Wrapper that tracks per-step fill counts and order submission counts."""
    market_trades = {
        product: [MarketTrade(t, t.quantity, t.quantity) for t in trades]
        for product, trades in data.trades[state.timestamp].items()
    }

    for product in data.products:
        s = stats[product]
        s["total_steps"] += 1

        product_orders = orders.get(product, [])
        s["orders_submitted"] += len(product_orders)

        new_trades = []
        for order in product_orders:
            qty_before = abs(order.quantity)
            if order.quantity > 0:
                fills = _tagged_match_buy(state, data, order, market_trades.get(product, []), mode)
            elif order.quantity < 0:
                fills = _tagged_match_sell(state, data, order, market_trades.get(product, []), mode)
            else:
                fills = []
            new_trades.extend(fills)

            # Track unfilled orders (order had leftover quantity)
            qty_after = abs(order.quantity)
            if qty_after > 0:
                s["orders_unfilled"] += 1

        if new_trades:
            state.own_trades[product] = new_trades
            result.trades.extend([TradeRow(trade) for trade in new_trades])
            s["steps_with_fills"] += 1
        else:
            state.own_trades[product] = []

    # Remaining market trades
    for product, trades in market_trades.items():
        for trade in trades:
            trade.trade.quantity = min(trade.buy_quantity, trade.sell_quantity)
        remaining = [t.trade for t in trades if t.trade.quantity > 0]
        state.market_trades[product] = remaining
        result.trades.extend([TradeRow(trade) for trade in remaining])


# ── Install patches ────────────────────────────────────────────────

runner.match_buy_order = _tagged_match_buy
runner.match_sell_order = _tagged_match_sell
runner.match_orders = _tagged_match_orders


# ── Report printer ─────────────────────────────────────────────────

def print_fill_report():
    if not stats:
        print("\nNo fills recorded.")
        return

    print("\n" + "=" * 72)
    print("  FILL ANALYTICS")
    print("=" * 72)

    for product in sorted(stats):
        s = stats[product]
        total_steps = s["total_steps"]

        maker_fills = s["maker_buys"] + s["maker_sells"]
        taker_fills = s["taker_buys"] + s["taker_sells"]
        total_fills = maker_fills + taker_fills

        maker_vol = s["maker_buy_vol"] + s["maker_sell_vol"]
        taker_vol = s["taker_buy_vol"] + s["taker_sell_vol"]
        total_vol = maker_vol + taker_vol

        maker_cost = s["maker_buy_cost"] + s["maker_sell_cost"]
        taker_cost = s["taker_buy_cost"] + s["taker_sell_cost"]

        print(f"\n  {product}")
        print(f"  {'─' * 60}")

        # Fill counts
        pct_m = maker_fills / total_fills * 100 if total_fills else 0
        pct_t = taker_fills / total_fills * 100 if total_fills else 0
        print(f"  Fills:   {total_fills:>6}  │  maker {maker_fills:>5} ({pct_m:5.1f}%)  │  taker {taker_fills:>5} ({pct_t:5.1f}%)")

        # Volume
        vpct_m = maker_vol / total_vol * 100 if total_vol else 0
        vpct_t = taker_vol / total_vol * 100 if total_vol else 0
        print(f"  Volume:  {total_vol:>6}  │  maker {maker_vol:>5} ({vpct_m:5.1f}%)  │  taker {taker_vol:>5} ({vpct_t:5.1f}%)")

        # Avg fill size
        avg_maker = maker_vol / maker_fills if maker_fills else 0
        avg_taker = taker_vol / taker_fills if taker_fills else 0
        avg_all = total_vol / total_fills if total_fills else 0
        print(f"  Avg qty: {avg_all:>6.1f}  │  maker {avg_maker:>5.1f}       │  taker {avg_taker:>5.1f}")

        # Avg price
        avg_maker_px = maker_cost / maker_vol if maker_vol else 0
        avg_taker_px = taker_cost / taker_vol if taker_vol else 0
        avg_all_px = (maker_cost + taker_cost) / total_vol if total_vol else 0
        print(f"  Avg px:  {avg_all_px:>8.1f}│  maker {avg_maker_px:>8.1f}   │  taker {avg_taker_px:>8.1f}")

        # Buy/sell breakdown
        print(f"  ┌─ Buys:  maker {s['maker_buys']:>4} ({s['maker_buy_vol']:>5} vol)  │  taker {s['taker_buys']:>4} ({s['taker_buy_vol']:>5} vol)")
        print(f"  └─ Sells: maker {s['maker_sells']:>4} ({s['maker_sell_vol']:>5} vol)  │  taker {s['taker_sells']:>4} ({s['taker_sell_vol']:>5} vol)")

        # Step-level stats
        fills_per_step = total_fills / total_steps if total_steps else 0
        vol_per_step = total_vol / total_steps if total_steps else 0
        fill_rate = s["steps_with_fills"] / total_steps * 100 if total_steps else 0
        print(f"  Steps:   {total_steps:>6}  │  with fills {s['steps_with_fills']:>5} ({fill_rate:5.1f}%)")
        print(f"  Per step: {fills_per_step:>5.2f} fills  │  {vol_per_step:>5.1f} vol")

        # Order efficiency
        submitted = s["orders_submitted"]
        unfilled = s["orders_unfilled"]
        fully_filled = submitted - unfilled
        fill_pct = fully_filled / submitted * 100 if submitted else 0
        print(f"  Orders:  {submitted:>6} submitted  │  {fully_filled:>5} fully filled ({fill_pct:5.1f}%)")

    print("\n" + "=" * 72)


# ── Main: delegate to backtester CLI, then print report ────────────

if __name__ == "__main__":
    from prosperity3bt.__main__ import app
    try:
        app(standalone_mode=False)
    except SystemExit:
        pass
    print_fill_report()
