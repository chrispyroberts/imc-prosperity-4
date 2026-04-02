import os
from contextlib import closing, redirect_stdout
from io import StringIO

from IPython.utils.io import Tee
from tqdm import tqdm

from prosperity3bt.data import DEFAULT_LIMIT, LIMITS, BacktestData, read_day_data
from prosperity3bt.datamodel import (
    ConversionObservation,
    Listing,
    Observation,
    Order,
    OrderDepth,
    Symbol,
    Trade,
    TradingState,
)
from prosperity3bt.file_reader import FileReader
from prosperity3bt.models import (
    ActivityLogRow,
    BacktestResult,
    MarketTrade,
    SandboxLogRow,
    TradeMatchingMode,
    TradeRow,
)


def prepare_state(state: TradingState, data: BacktestData) -> None:
    for product in data.products:
        order_depth = OrderDepth()
        row = data.prices[state.timestamp][product]

        for price, volume in zip(row.bid_prices, row.bid_volumes):
            order_depth.buy_orders[price] = volume

        for price, volume in zip(row.ask_prices, row.ask_volumes):
            order_depth.sell_orders[price] = -volume

        state.order_depths[product] = order_depth

        state.listings[product] = Listing(product, product, 1)

    observation_row = data.observations.get(state.timestamp)

    if observation_row is None:
        state.observations = Observation({}, {})
    else:
        conversion_observation = ConversionObservation(
            bidPrice=observation_row.bidPrice,
            askPrice=observation_row.askPrice,
            transportFees=observation_row.transportFees,
            exportTariff=observation_row.exportTariff,
            importTariff=observation_row.importTariff,
            sugarPrice=observation_row.sugarPrice,
            sunlightIndex=observation_row.sunlightIndex,
        )

        state.observations = Observation(
            plainValueObservations={}, conversionObservations={"MAGNIFICENT_MACARONS": conversion_observation}
        )


def type_check_orders(orders: dict[Symbol, list[Order]]) -> None:
    for key, value in orders.items():
        if not isinstance(key, str):
            raise ValueError(f"Orders key '{key}' is of type {type(key)}, expected a str")

        for order in value:
            if not isinstance(order.symbol, str):
                raise ValueError(f"Order symbol of '{order}' is of type {type(order.symbol)}, expected a str")

            if not isinstance(order.price, int):
                raise ValueError(f"Order price of '{order}' is of type {type(order.price)}, expected an int")

            if not isinstance(order.quantity, int):
                raise ValueError(f"Order quantity of '{order}' is of type {type(order.quantity)}, expected an int")


def create_activity_logs(
    state: TradingState,
    data: BacktestData,
    result: BacktestResult,
) -> None:
    for product in data.products:
        row = data.prices[state.timestamp][product]

        product_profit_loss = data.profit_loss[product]

        position = state.position.get(product, 0)
        if position != 0:
            product_profit_loss += position * row.mid_price

        bid_prices_len = len(row.bid_prices)
        bid_volumes_len = len(row.bid_volumes)
        ask_prices_len = len(row.ask_prices)
        ask_volumes_len = len(row.ask_volumes)

        columns = [
            result.day_num,
            state.timestamp,
            product,
            row.bid_prices[0] if bid_prices_len > 0 else "",
            row.bid_volumes[0] if bid_volumes_len > 0 else "",
            row.bid_prices[1] if bid_prices_len > 1 else "",
            row.bid_volumes[1] if bid_volumes_len > 1 else "",
            row.bid_prices[2] if bid_prices_len > 2 else "",
            row.bid_volumes[2] if bid_volumes_len > 2 else "",
            row.ask_prices[0] if ask_prices_len > 0 else "",
            row.ask_volumes[0] if ask_volumes_len > 0 else "",
            row.ask_prices[1] if ask_prices_len > 1 else "",
            row.ask_volumes[1] if ask_volumes_len > 1 else "",
            row.ask_prices[2] if ask_prices_len > 2 else "",
            row.ask_volumes[2] if ask_volumes_len > 2 else "",
            row.mid_price,
            product_profit_loss,
        ]

        result.activity_logs.append(ActivityLogRow(columns))


def enforce_limits(
    state: TradingState,
    data: BacktestData,
    orders: dict[Symbol, list[Order]],
    sandbox_row: SandboxLogRow,
) -> None:
    sandbox_log_lines = []
    for product in data.products:
        product_orders = orders.get(product, [])
        product_position = state.position.get(product, 0)

        total_long = sum(order.quantity for order in product_orders if order.quantity > 0)
        total_short = sum(abs(order.quantity) for order in product_orders if order.quantity < 0)

        limit = LIMITS.get(product, DEFAULT_LIMIT)
        if product_position + total_long > limit or product_position - total_short < -limit:
            sandbox_log_lines.append(f"Orders for product {product} exceeded limit of {limit} set")
            orders.pop(product)

    if len(sandbox_log_lines) > 0:
        sandbox_row.sandbox_log += "\n" + "\n".join(sandbox_log_lines)


def match_buy_order(
    state: TradingState,
    data: BacktestData,
    order: Order,
    market_trades: list[MarketTrade],
    trade_matching_mode: TradeMatchingMode,
) -> list[Trade]:
    trades = []

    order_depth = state.order_depths[order.symbol]
    price_matches = sorted(price for price in order_depth.sell_orders.keys() if price <= order.price)
    for price in price_matches:
        volume = min(order.quantity, abs(order_depth.sell_orders[price]))

        trades.append(Trade(order.symbol, price, volume, "SUBMISSION", "", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= price * volume

        order_depth.sell_orders[price] += volume
        if order_depth.sell_orders[price] == 0:
            order_depth.sell_orders.pop(price)

        order.quantity -= volume
        if order.quantity == 0:
            return trades

    if trade_matching_mode == TradeMatchingMode.none:
        return trades

    for market_trade in market_trades:
        if (
            market_trade.sell_quantity == 0
            or market_trade.trade.price > order.price
            or (market_trade.trade.price == order.price and trade_matching_mode == TradeMatchingMode.worse)
        ):
            continue

        volume = min(order.quantity, market_trade.sell_quantity)

        trades.append(
            Trade(order.symbol, order.price, volume, "SUBMISSION", market_trade.trade.seller, state.timestamp)
        )

        state.position[order.symbol] = state.position.get(order.symbol, 0) + volume
        data.profit_loss[order.symbol] -= order.price * volume

        market_trade.sell_quantity -= volume

        order.quantity -= volume
        if order.quantity == 0:
            return trades

    return trades


def match_sell_order(
    state: TradingState,
    data: BacktestData,
    order: Order,
    market_trades: list[MarketTrade],
    trade_matching_mode: TradeMatchingMode,
) -> list[Trade]:
    trades = []

    order_depth = state.order_depths[order.symbol]
    price_matches = sorted((price for price in order_depth.buy_orders.keys() if price >= order.price), reverse=True)
    for price in price_matches:
        volume = min(abs(order.quantity), order_depth.buy_orders[price])

        trades.append(Trade(order.symbol, price, volume, "", "SUBMISSION", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += price * volume

        order_depth.buy_orders[price] -= volume
        if order_depth.buy_orders[price] == 0:
            order_depth.buy_orders.pop(price)

        order.quantity += volume
        if order.quantity == 0:
            return trades

    if trade_matching_mode == TradeMatchingMode.none:
        return trades

    for market_trade in market_trades:
        if (
            market_trade.buy_quantity == 0
            or market_trade.trade.price < order.price
            or (market_trade.trade.price == order.price and trade_matching_mode == TradeMatchingMode.worse)
        ):
            continue

        volume = min(abs(order.quantity), market_trade.buy_quantity)

        trades.append(Trade(order.symbol, order.price, volume, market_trade.trade.buyer, "SUBMISSION", state.timestamp))

        state.position[order.symbol] = state.position.get(order.symbol, 0) - volume
        data.profit_loss[order.symbol] += order.price * volume

        market_trade.buy_quantity -= volume

        order.quantity += volume
        if order.quantity == 0:
            return trades

    return trades


def match_order(
    state: TradingState,
    data: BacktestData,
    order: Order,
    market_trades: list[MarketTrade],
    trade_matching_mode: TradeMatchingMode,
) -> list[Trade]:
    if order.quantity > 0:
        return match_buy_order(state, data, order, market_trades, trade_matching_mode)
    elif order.quantity < 0:
        return match_sell_order(state, data, order, market_trades, trade_matching_mode)
    else:
        return []


def match_orders(
    state: TradingState,
    data: BacktestData,
    orders: dict[Symbol, list[Order]],
    result: BacktestResult,
    trade_matching_mode: TradeMatchingMode,
) -> None:
    market_trades = {
        product: [MarketTrade(t, t.quantity, t.quantity) for t in trades]
        for product, trades in data.trades[state.timestamp].items()
    }

    for product in data.products:
        new_trades = []

        for order in orders.get(product, []):
            new_trades.extend(
                match_order(
                    state,
                    data,
                    order,
                    market_trades.get(product, []),
                    trade_matching_mode,
                )
            )

        if len(new_trades) > 0:
            state.own_trades[product] = new_trades
            result.trades.extend([TradeRow(trade) for trade in new_trades])

    for product, trades in market_trades.items():
        for trade in trades:
            trade.trade.quantity = min(trade.buy_quantity, trade.sell_quantity)

        remaining_market_trades = [t.trade for t in trades if t.trade.quantity > 0]

        state.market_trades[product] = remaining_market_trades
        result.trades.extend([TradeRow(trade) for trade in remaining_market_trades])


def run_backtest(
    trader,
    file_reader: FileReader,
    round_num: int,
    day_num: int,
    print_output: bool,
    trade_matching_mode: TradeMatchingMode,
    no_names: bool,
    show_progress_bar: bool,
) -> BacktestResult:
    data = read_day_data(file_reader, round_num, day_num, no_names)

    os.environ["PROSPERITY3BT_ROUND"] = str(round_num)
    os.environ["PROSPERITY3BT_DAY"] = str(day_num)

    trader_data = ""
    state = TradingState(
        traderData=trader_data,
        timestamp=0,
        listings={},
        order_depths={},
        own_trades={},
        market_trades={},
        position={},
        observations=Observation({}, {}),
    )

    result = BacktestResult(
        round_num=data.round_num,
        day_num=data.day_num,
        sandbox_logs=[],
        activity_logs=[],
        trades=[],
    )

    timestamps = sorted(data.prices.keys())
    timestamps_iterator = tqdm(timestamps, ascii=True) if show_progress_bar else timestamps

    for timestamp in timestamps_iterator:
        state.timestamp = timestamp
        state.traderData = trader_data

        prepare_state(state, data)

        stdout = StringIO()

        # Tee calls stdout.close(), making stdout.getvalue() impossible
        # This override makes getvalue() possible after close()
        stdout.close = lambda: None  # type: ignore[method-assign]

        if print_output:
            with closing(Tee(stdout)):
                orders, conversions, trader_data = trader.run(state)
        else:
            with redirect_stdout(stdout):
                orders, conversions, trader_data = trader.run(state)

        sandbox_row = SandboxLogRow(
            timestamp=timestamp,
            sandbox_log="",
            lambda_log=stdout.getvalue().rstrip(),
        )

        result.sandbox_logs.append(sandbox_row)

        type_check_orders(orders)
        create_activity_logs(state, data, result)
        enforce_limits(state, data, orders, sandbox_row)
        match_orders(state, data, orders, result, trade_matching_mode)

    return result
