#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import signal
import sys
import traceback
import types
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKTESTER_ROOT = ROOT / "backtester"
sys.path.insert(0, str(BACKTESTER_ROOT))
sys.path.insert(0, str(ROOT))

try:
    import jsonpickle  # noqa: F401
except ModuleNotFoundError:
    jsonpickle_stub = types.ModuleType("jsonpickle")
    jsonpickle_stub.encode = lambda value: json.dumps(  # type: ignore[attr-defined]
        value,
        default=lambda inner: getattr(inner, "__dict__", str(inner)),
    )
    sys.modules["jsonpickle"] = jsonpickle_stub

from prosperity4mcbt import datamodel as datamodel_module  # noqa: E402

sys.modules.setdefault("datamodel", datamodel_module)
sys.modules.setdefault("prosperity3bt.datamodel", datamodel_module)
sys.modules.setdefault("prosperity4mcbt.datamodel", datamodel_module)


def load_trader(strategy_path: Path):
    sys.path.insert(0, str(strategy_path.parent))
    spec = importlib.util.spec_from_file_location(f"strategy_{strategy_path.stem}", strategy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to import strategy from {strategy_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    trader_cls = getattr(module, "Trader", None)
    if trader_cls is None:
        raise RuntimeError(f"{strategy_path} does not define Trader")
    return trader_cls()


@contextmanager
def run_timeout(timeout_ms: int):
    if timeout_ms <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    timeout_seconds = timeout_ms / 1000.0

    def handle_timeout(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"Trader.run timed out after {timeout_ms} ms")

    previous_handler = signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def build_observation(payload: dict[str, Any] | None):
    if not payload:
        return datamodel_module.Observation({}, {})

    plain = payload.get("plain_value_observations", payload.get("plainValueObservations", {}))
    raw_conversion_observations = payload.get(
        "conversion_observations", payload.get("conversionObservations", {})
    )
    conversions = {}
    for product, observation in raw_conversion_observations.items():
        conversions[product] = datamodel_module.ConversionObservation(
            float(observation["bidPrice"]),
            float(observation["askPrice"]),
            float(observation["transportFees"]),
            float(observation["exportTariff"]),
            float(observation["importTariff"]),
            float(observation["sugarPrice"]),
            float(observation["sunlightIndex"]),
        )
    return datamodel_module.Observation(plain, conversions)


def build_order_depth(payload: dict[str, Any]):
    depth = datamodel_module.OrderDepth()
    depth.buy_orders = {int(price): int(qty) for price, qty in payload.get("buy_orders", {}).items()}
    depth.sell_orders = {int(price): int(qty) for price, qty in payload.get("sell_orders", {}).items()}
    return depth


def build_trade(payload: dict[str, Any]):
    return datamodel_module.Trade(
        payload["symbol"],
        int(payload["price"]),
        int(payload["quantity"]),
        payload.get("buyer"),
        payload.get("seller"),
        int(payload["timestamp"]),
    )


def build_state(payload: dict[str, Any]):
    products = sorted(payload["order_depths"].keys())
    listings = {product: datamodel_module.Listing(product, product, "XIRECS") for product in products}
    order_depths = {product: build_order_depth(depth) for product, depth in payload["order_depths"].items()}
    own_trades = {
        product: [build_trade(trade) for trade in payload.get("own_trades", {}).get(product, [])]
        for product in products
    }
    market_trades = {
        product: [build_trade(trade) for trade in payload.get("market_trades", {}).get(product, [])]
        for product in products
    }
    position = {product: int(pos) for product, pos in payload.get("position", {}).items()}
    observations = build_observation(payload.get("observations"))
    return datamodel_module.TradingState(
        traderData=payload.get("trader_data", ""),
        timestamp=int(payload["timestamp"]),
        listings=listings,
        order_depths=order_depths,
        own_trades=own_trades,
        market_trades=market_trades,
        position=position,
        observations=observations,
    )


def serialize_orders(result: dict[str, list[Any]]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    for product, orders in result.items():
        output[product] = [
            {"symbol": order.symbol, "price": int(order.price), "quantity": int(order.quantity)}
            for order in orders
        ]
    return output


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: python_strategy_worker.py <strategy.py>"}), flush=True)
        return 1

    strategy_path = Path(sys.argv[1]).resolve()
    trader = load_trader(strategy_path)

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        request = json.loads(raw_line)
        request_type = request.get("type", "run")

        try:
            if request_type == "reset":
                trader = load_trader(strategy_path)
                response = {"ok": True}
            elif request_type == "run":
                state = build_state(request)
                timeout_ms = int(request.get("timeout_ms", 900))
                stdout = io.StringIO()
                with redirect_stdout(stdout), run_timeout(timeout_ms):
                    result, conversions, trader_data = trader.run(state)
                response = {
                    "orders": serialize_orders(result),
                    "conversions": int(conversions),
                    "trader_data": trader_data,
                    "stdout": stdout.getvalue(),
                }
            else:
                response = {"error": f"unsupported request type {request_type}"}
        except Exception:
            response = {"error": traceback.format_exc()}

        print(json.dumps(response, separators=(",", ":")), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
