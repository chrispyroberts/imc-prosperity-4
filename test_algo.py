import json
from prosperity3bt.datamodel import OrderDepth, TradingState, Order


class Trader:
    """Simple market maker for testing the backtester with Prosperity 4 data."""

    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders = []

            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None

            if best_bid is not None and best_ask is not None:
                mid = (best_bid + best_ask) / 2
                spread = best_ask - best_bid
                position = state.position.get(product, 0)

                # Market make around mid price, skew based on position
                skew = -position * 0.1
                buy_price = int(mid - spread / 4 + skew)
                sell_price = int(mid + spread / 4 + skew)

                buy_qty = min(10, 80 - position)
                sell_qty = min(10, 80 + position)

                if buy_qty > 0:
                    orders.append(Order(product, buy_price, buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, sell_price, -sell_qty))

            result[product] = orders

        return result, 0, ""
