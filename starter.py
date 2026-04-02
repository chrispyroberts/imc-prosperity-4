from prosperity3bt.datamodel import OrderDepth, TradingState, Order


class Trader:
    def run(self, state: TradingState):
        result = {}

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders = []

            if len(order_depth.sell_orders) > 0:
                best_ask = min(order_depth.sell_orders.keys())
                best_ask_volume = order_depth.sell_orders[best_ask]
                # Buy at the best ask if it seems cheap
                if product == "EMERALDS" and best_ask < 10000:
                    orders.append(Order(product, best_ask, -best_ask_volume))
                elif product == "TOMATOES" and best_ask < 5006:
                    orders.append(Order(product, best_ask, -best_ask_volume))

            if len(order_depth.buy_orders) > 0:
                best_bid = max(order_depth.buy_orders.keys())
                best_bid_volume = order_depth.buy_orders[best_bid]
                # Sell at the best bid if it seems expensive
                if product == "EMERALDS" and best_bid > 10000:
                    orders.append(Order(product, best_bid, -best_bid_volume))
                elif product == "TOMATOES" and best_bid > 5006:
                    orders.append(Order(product, best_bid, -best_bid_volume))

            result[product] = orders

        return result, 0, ""
