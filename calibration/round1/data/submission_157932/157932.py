try:
    from datamodel import Order, OrderDepth, TradingState, Symbol, Listing, Observation, Trade
except ImportError:
    from prosperity3bt.datamodel import Order, OrderDepth, TradingState, Symbol, Listing, Observation, Trade

import json

# round 1 hold-1 probe for server FV recovery.
# buys exactly 1 of each product as soon as the book allows, then holds forever.
# fv(t) = pnl(t) + buy_price per product, per chrispy's calibration recipe.
PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]


class Logger:
    def __init__(self): self.logs = ""
    def print(self, *args, **kwargs):
        self.logs += " ".join(map(str, args)) + "\n"
    def flush(self, state, orders, conversions, trader_data):
        base_length = len(self.to_json([self.compress_state(state, ""), self.compress_orders(orders), conversions, "", ""]))
        max_item_length = (3750 - base_length) // 3
        print(self.to_json([self.compress_state(state, self.truncate(state.traderData, max_item_length)), self.compress_orders(orders), conversions, self.truncate(trader_data, max_item_length), self.truncate(self.logs, max_item_length)]))
        self.logs = ""
    def compress_state(self, state, trader_data):
        return [state.timestamp, trader_data, self.compress_listings(state.listings), self.compress_order_depths(state.order_depths), self.compress_trades(state.own_trades), self.compress_trades(state.market_trades), state.position, self.compress_observations(state.observations)]
    def compress_listings(self, listings):
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]
    def compress_order_depths(self, order_depths):
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}
    def compress_trades(self, trades):
        return [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for arr in trades.values() for t in arr]
    def compress_observations(self, obs):
        co = {}
        for p, o in obs.conversionObservations.items():
            co[p] = [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
        return [obs.plainValueObservations, co]
    def compress_orders(self, orders):
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]
    def to_json(self, value):
        return json.dumps(value, separators=(",", ":"))
    def truncate(self, value, max_length):
        return value[:max_length - 3] + "..." if len(value) > max_length else value


logger = Logger()


class Trader:
    def run(self, state: TradingState):
        orders = {p: [] for p in state.order_depths}

        # keep retrying until we hold exactly 1 of each, in case first-tick book is empty.
        for product in PRODUCTS:
            pos = state.position.get(product, 0)
            if pos >= 1:
                continue
            ob = state.order_depths.get(product)
            if not ob or not ob.sell_orders:
                continue
            best_ask = min(ob.sell_orders.keys())
            orders.setdefault(product, []).append(Order(product, best_ask, 1))

        trader_data = ""
        logger.flush(state, orders, 0, trader_data)
        return orders, 0, trader_data