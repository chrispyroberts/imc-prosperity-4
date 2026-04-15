"""Round 1 starter strategy.

Combines the two community-consensus baselines, both grounded in the
calibration findings documented in `calibration/round1/FINDINGS.md`:

    ASH_COATED_OSMIUM  -- MM around fv=10000 with a tight spread.
                          Justified by OSMIUM's MeanRevertOU FV process
                          (center=9999.25, half-life ~18 ticks).

    INTARIAN_PEPPER_ROOT -- buy and hold to the position limit.
                            Justified by PEPPER's stable positive drift
                            of ~0.091/tick (~91/day, stable across
                            training days -2/-1/0).

Everything is product-agnostic in the control flow: the trader looks up
each product in state.order_depths and applies the matching policy. No
hardcoded product list outside the strategy-parameter table.

Target on day 1 eval with position limit 80 per product:
  - OSMIUM: ~3k XIRECS (MM spread capture, noisy)
  - PEPPER: ~7.3k XIRECS (80 units * ~91/day drift)
  - Total:  ~10k XIRECS (community benchmark baseline)
"""

from prosperity3bt.datamodel import OrderDepth, TradingState, Order


POSITION_LIMIT = 80

# per-product policy parameters. driven by FINDINGS.md.
# OSMIUM: MM around a hardcoded fair value; post one tick inside bot2.
# PEPPER: buy-hold; post aggressive buys until we hit the position limit,
# then sit.
STRATEGY = {
    "ASH_COATED_OSMIUM": {
        "kind": "market_make",
        "fair": 10000,
        "spread": 2,  # post bid at fair - 1, ask at fair + 1 (spread 2)
    },
    "INTARIAN_PEPPER_ROOT": {
        "kind": "buy_hold",
    },
}


class Trader:
    def run(self, state: TradingState):
        result: dict[str, list[Order]] = {}

        for product in state.order_depths:
            cfg = STRATEGY.get(product)
            if cfg is None:
                # unknown product: skip cleanly rather than crash. lets
                # the same file run on tutorial, round 1, and future rounds
                # without edits until the strategy table is extended.
                result[product] = []
                continue

            pos = state.position.get(product, 0)
            depth = state.order_depths[product]

            if cfg["kind"] == "market_make":
                result[product] = self._market_make(product, cfg, depth, pos)
            elif cfg["kind"] == "buy_hold":
                result[product] = self._buy_hold(product, depth, pos)
            else:
                result[product] = []

        return result, 0, ""

    def _market_make(self, product: str, cfg: dict, depth: OrderDepth, pos: int) -> list[Order]:
        """Post a 2-tick spread around the hardcoded fair value.

        Skip any side where we'd breach the position limit. If the book
        shows a crossable price (someone bidding above fair or asking
        below fair), take that first before posting.
        """
        orders: list[Order] = []
        fair = cfg["fair"]
        half_spread = cfg["spread"] // 2

        # opportunistic take: any ask < fair - 1 is a gift.
        if depth.sell_orders:
            best_ask = min(depth.sell_orders.keys())
            best_ask_vol = depth.sell_orders[best_ask]  # negative: -10 means 10 for sale
            if best_ask < fair - 1 and pos < POSITION_LIMIT:
                qty = min(-best_ask_vol, POSITION_LIMIT - pos)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))

        # opportunistic take: any bid > fair + 1 is a gift.
        if depth.buy_orders:
            best_bid = max(depth.buy_orders.keys())
            best_bid_vol = depth.buy_orders[best_bid]  # positive
            if best_bid > fair + 1 and pos > -POSITION_LIMIT:
                qty = min(best_bid_vol, POSITION_LIMIT + pos)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

        # passive quotes inside bot 2's spread.
        post_bid = fair - half_spread
        post_ask = fair + half_spread
        buy_capacity = POSITION_LIMIT - pos
        sell_capacity = POSITION_LIMIT + pos
        if buy_capacity > 0:
            orders.append(Order(product, post_bid, buy_capacity))
        if sell_capacity > 0:
            orders.append(Order(product, post_ask, -sell_capacity))

        return orders

    def _buy_hold(self, product: str, depth: OrderDepth, pos: int) -> list[Order]:
        """Buy up to the position limit at the best available ask and hold.

        PEPPER is thin on the buy-side; we lift whatever sits on offer
        until we're full. We never sell; the drift is positive so any
        mark-to-market loss is expected to recover.
        """
        remaining = POSITION_LIMIT - pos
        if remaining <= 0 or not depth.sell_orders:
            return []

        orders: list[Order] = []
        # take each ask level from cheapest to most expensive until we're
        # full or the book runs out. walking the book slightly overpays on
        # thin-liquidity days but guarantees we hit the limit.
        for ask_price in sorted(depth.sell_orders.keys()):
            if remaining <= 0:
                break
            available = -depth.sell_orders[ask_price]  # negative volume
            qty = min(remaining, available)
            if qty > 0:
                orders.append(Order(product, ask_price, qty))
                remaining -= qty

        return orders
