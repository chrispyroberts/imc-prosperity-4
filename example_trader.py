"""
Official IMC Prosperity 4 Starter Trader
=========================================
This is the example trader template provided by IMC on the Prosperity wiki.
The only thing you need to change is the `acceptable_price` calculation —
right now it's hardcoded to 10, which is obviously wrong for EMERALDS (~10,000)
and TOMATOES (~5,000).

Usage:
    cd prosperity4
    source backtester/.venv/bin/activate
    prosperity4mcbt example_trader.py --quick
    prosperity3bt example_trader.py 0 --data data --print --no-out

This file is intentionally left in the official starter shape, and
`prosperity4mcbt` can run it unchanged.
"""

from typing import List
import string
from prosperity3bt.datamodel import OrderDepth, UserId, TradingState, Order


class Trader:

    def run(self, state: TradingState):
        print("traderData: " + state.traderData)
        print("Observations: " + str(state.observations))

        result = {}
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            acceptable_price = 10  # Participant should calculate this value
            print("Acceptable price : " + str(acceptable_price))
            print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))

            if len(order_depth.sell_orders) != 0:
                best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
                if int(best_ask) < acceptable_price:
                    print("BUY", str(-best_ask_amount) + "x", best_ask)
                    orders.append(Order(product, best_ask, -best_ask_amount))

            if len(order_depth.buy_orders) != 0:
                best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
                if int(best_bid) > acceptable_price:
                    print("SELL", str(best_bid_amount) + "x", best_bid)
                    orders.append(Order(product, best_bid, -best_bid_amount))

            result[product] = orders

        traderData = "SAMPLE"
        conversions = 1
        return result, conversions, traderData
