import sys
from collections import defaultdict
from datetime import datetime
from functools import reduce
from importlib import import_module, metadata, reload
from pathlib import Path
from typing import Annotated, Any, Optional

from typer import Argument, Option, Typer

from prosperity3bt.data import has_day_data
from prosperity3bt.file_reader import FileReader, FileSystemReader, PackageResourcesReader
from prosperity3bt.monte_carlo import default_dashboard_path, normalize_dashboard_path, run_monte_carlo_mode
from prosperity3bt.models import BacktestResult, TradeMatchingMode
from prosperity3bt.open import open_monte_carlo_visualizer, open_visualizer
from prosperity3bt.runner import run_backtest


def parse_algorithm(algorithm: Path) -> Any:
    sys.path.append(str(algorithm.parent))
    return import_module(algorithm.stem)


def parse_data(data_root: Optional[Path]) -> FileReader:
    if data_root is not None:
        return FileSystemReader(data_root)
    else:
        return PackageResourcesReader()


def parse_days(file_reader: FileReader, days: list[str]) -> list[tuple[int, int]]:
    parsed_days = []

    for arg in days:
        if "-" in arg:
            round_num, day_num = map(int, arg.split("-", 1))

            if not has_day_data(file_reader, round_num, day_num):
                print(f"Warning: no data found for round {round_num} day {day_num}")
                continue

            parsed_days.append((round_num, day_num))
        else:
            round_num = int(arg)

            parsed_days_in_round = []
            for day_num in range(-5, 100):
                if has_day_data(file_reader, round_num, day_num):
                    parsed_days_in_round.append((round_num, day_num))

            if len(parsed_days_in_round) == 0:
                print(f"Warning: no data found for round {round_num}")
                continue

            parsed_days.extend(parsed_days_in_round)

    if len(parsed_days) == 0:
        print("Error: did not find data for any requested round/day")
        sys.exit(1)

    return parsed_days


def parse_out(out: Optional[Path], no_out: bool) -> Optional[Path]:
    if out is not None:
        return out

    if no_out:
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path.cwd() / "backtests" / f"{timestamp}.log"


def print_day_summary(result: BacktestResult) -> None:
    last_timestamp = result.activity_logs[-1].timestamp

    product_lines = []
    total_profit = 0

    for row in reversed(result.activity_logs):
        if row.timestamp != last_timestamp:
            break

        product = row.columns[2]
        profit = row.columns[-1]

        product_lines.append(f"{product}: {profit:,.0f}")
        total_profit += profit

    print(*reversed(product_lines), sep="\n")
    print(f"Total profit: {total_profit:,.0f}")


def merge_results(
    a: BacktestResult, b: BacktestResult, merge_profit_loss: bool, merge_timestamps: bool
) -> BacktestResult:
    sandbox_logs = a.sandbox_logs[:]
    activity_logs = a.activity_logs[:]
    trades = a.trades[:]

    if merge_timestamps:
        a_last_timestamp = a.activity_logs[-1].timestamp
        timestamp_offset = a_last_timestamp + 100
    else:
        timestamp_offset = 0

    sandbox_logs.extend([row.with_offset(timestamp_offset) for row in b.sandbox_logs])
    trades.extend([row.with_offset(timestamp_offset) for row in b.trades])

    if merge_profit_loss:
        profit_loss_offsets = defaultdict(float)
        for row in reversed(a.activity_logs):
            if row.timestamp != a_last_timestamp:
                break

            profit_loss_offsets[row.columns[2]] = row.columns[-1]

        activity_logs.extend(
            [row.with_offset(timestamp_offset, profit_loss_offsets[row.columns[2]]) for row in b.activity_logs]
        )
    else:
        activity_logs.extend([row.with_offset(timestamp_offset, 0) for row in b.activity_logs])

    return BacktestResult(a.round_num, a.day_num, sandbox_logs, activity_logs, trades)


def write_output(output_file: Path, merged_results: BacktestResult) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w+", encoding="utf-8") as file:
        file.write("Sandbox logs:\n")
        for row in merged_results.sandbox_logs:
            file.write(str(row))

        file.write("\n\n\nActivities log:\n")
        file.write(
            "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;mid_price;profit_and_loss\n"
        )
        file.write("\n".join(map(str, merged_results.activity_logs)))

        file.write("\n\n\n\n\nTrade History:\n")
        file.write("[\n")
        file.write(",\n".join(map(str, merged_results.trades)))
        file.write("]")


def print_overall_summary(results: list[BacktestResult]) -> None:
    print("Profit summary:")

    total_profit = 0
    for result in results:
        last_timestamp = result.activity_logs[-1].timestamp

        profit = 0
        for row in reversed(result.activity_logs):
            if row.timestamp != last_timestamp:
                break

            profit += row.columns[-1]

        print(f"Round {result.round_num} day {result.day_num}: {profit:,.0f}")
        total_profit += profit

    print(f"Total profit: {total_profit:,.0f}")


def format_path(path: Path) -> str:
    cwd = Path.cwd()
    if path.is_relative_to(cwd):
        return str(path.relative_to(cwd))
    else:
        return str(path)


def version_callback(value: bool) -> None:
    if value:
        print(f"prosperity3bt {metadata.version(__package__)}")
        sys.exit(0)


app = Typer(context_settings={"help_option_names": ["--help", "-h"]})
mc_app = Typer(context_settings={"help_option_names": ["--help", "-h"]})


@app.command()
def cli(
    algorithm: Annotated[Path, Argument(help="Path to the Python file containing the algorithm to backtest.", show_default=False, exists=True, file_okay=True, dir_okay=False, resolve_path=True)],
    days: Annotated[list[str], Argument(help="The days to backtest on. <round>-<day> for a single day, <round> for all days in a round.", show_default=False)],
    merge_pnl: Annotated[bool, Option("--merge-pnl", help="Merge profit and loss across days.")] = False,
    vis: Annotated[bool, Option("--vis", help="Open results in the local visualizer when done. Replay logs are no longer supported by the bundled frontend.")] = False,
    out: Annotated[Optional[Path], Option(help="File to save output log to (defaults to backtests/<timestamp>.log).", show_default=False, dir_okay=False, resolve_path=True)] = None,
    no_out: Annotated[bool, Option("--no-out", help="Skip saving output log.")] = False,
    data: Annotated[Optional[Path], Option(help="Path to data directory. Must look similar in structure to https://github.com/jmerle/imc-prosperity-3-backtester/tree/master/prosperity3bt/resources.", show_default=False, exists=True, file_okay=False, dir_okay=True, resolve_path=True)] = None,
    print_output: Annotated[bool, Option("--print", help="Print the trader's output to stdout while it's running.")] = False,
    match_trades: Annotated[TradeMatchingMode, Option(help="How to match orders against market trades. 'all' matches trades with prices equal to or worse than your quotes, 'worse' matches trades with prices worse than your quotes, 'none' does not match trades against orders at all.")] = TradeMatchingMode.all,
    no_progress: Annotated[bool, Option("--no-progress", help="Don't show progress bars.")] = False,
    original_timestamps: Annotated[bool, Option("--original-timestamps", help="Preserve original timestamps in output log rather than making them increase across days.")] = False,
    version: Annotated[bool, Option("--version", "-v", help="Show the program's version number and exit.", is_eager=True, callback=version_callback)] = False,
) -> None:  # fmt: skip
    if out is not None and no_out:
        print("Error: --out and --no-out are mutually exclusive")
        sys.exit(1)

    try:
        trader_module = parse_algorithm(algorithm)
    except ModuleNotFoundError as e:
        print(f"{algorithm} is not a valid algorithm file: {e}")
        sys.exit(1)

    if not hasattr(trader_module, "Trader"):
        print(f"{algorithm} does not expose a Trader class")
        sys.exit(1)

    file_reader = parse_data(data)
    parsed_days = parse_days(file_reader, days)
    output_file = parse_out(out, no_out)

    show_progress_bars = not no_progress and not print_output

    results = []
    for round_num, day_num in parsed_days:
        print(f"Backtesting {algorithm} on round {round_num} day {day_num}")

        reload(trader_module)

        result = run_backtest(
            trader_module.Trader(),
            file_reader,
            round_num,
            day_num,
            print_output,
            match_trades,
            True,
            show_progress_bars,
        )

        print_day_summary(result)
        if len(parsed_days) > 1:
            print()

        results.append(result)

    if len(parsed_days) > 1:
        print_overall_summary(results)

    if output_file is not None:
        merged_results = reduce(lambda a, b: merge_results(a, b, merge_pnl, not original_timestamps), results)
        write_output(output_file, merged_results)
        print(f"\nSuccessfully saved backtest results to {format_path(output_file)}")

    if vis and output_file is not None:
        open_visualizer(output_file)


@mc_app.command()
def monte_carlo_cli(
    algorithm: Annotated[Path, Argument(help="Path to the Python file containing the algorithm to backtest.", show_default=False, exists=True, file_okay=True, dir_okay=False, resolve_path=True)],
    vis: Annotated[bool, Option("--vis", help="Open Monte Carlo dashboard in the local visualizer when done.")] = False,
    out: Annotated[Optional[Path], Option(help="Path to dashboard JSON file (defaults to backtests/<timestamp>_monte_carlo/dashboard.json).", show_default=False, resolve_path=True)] = None,
    no_out: Annotated[bool, Option("--no-out", help="Skip saving dashboard output.")] = False,
    data: Annotated[Optional[Path], Option(help="Path to data directory. If it contains round0/, that round0 directory is used as the actual calibration source.", show_default=False, exists=True, file_okay=False, dir_okay=True, resolve_path=True)] = None,
    quick: Annotated[bool, Option("--quick", help="Preset for a fast run: 100 sessions and 10 sample sessions.")] = False,
    heavy: Annotated[bool, Option("--heavy", help="Preset for a full run: 1000 sessions and 100 sample sessions.")] = False,
    sessions: Annotated[int, Option("--sessions", help="Number of Monte Carlo sessions to run.")] = 100,
    fv_mode: Annotated[str, Option("--fv-mode", help="Fair-value mode for the Rust simulator.")] = "simulate",
    trade_mode: Annotated[str, Option("--trade-mode", help="Trade-arrival mode for the Rust simulator.")] = "simulate",
    tomato_support: Annotated[str, Option("--tomato-support", help="Latent fair support for tomatoes in simulate mode.")] = "continuous",
    seed: Annotated[int, Option("--seed", help="RNG seed for the Rust simulator.")] = 20260401,
    python_bin: Annotated[str, Option("--python-bin", help="Python interpreter used for the strategy worker process.")] = sys.executable,
    sample_sessions: Annotated[int, Option("--sample-sessions", help="Number of sessions to persist with full path/trace data for dashboard charts.")] = 10,
    ticks_per_day: Annotated[int, Option("--ticks-per-day", help="Number of ticks per simulated day (server=2000, training=10000).")] = 10000,
) -> None:
    if no_out:
        print("Error: Monte Carlo mode always writes a dashboard bundle, so --no-out is not supported")
        sys.exit(1)
    if quick and heavy:
        print("Error: --quick and --heavy are mutually exclusive")
        sys.exit(1)

    if quick:
        sessions = 100
        sample_sessions = 10
    elif heavy:
        sessions = 1000
        sample_sessions = 100

    dashboard_path = normalize_dashboard_path(out, False) or default_dashboard_path()

    dashboard = run_monte_carlo_mode(
        algorithm=algorithm,
        dashboard_path=dashboard_path,
        data_root=data,
        sessions=sessions,
        fv_mode=fv_mode,
        trade_mode=trade_mode,
        tomato_support=tomato_support,
        seed=seed,
        python_bin=python_bin,
        sample_sessions=sample_sessions,
        ticks_per_day=ticks_per_day,
    )

    total_stats = dashboard["overall"]["totalPnl"]
    print(f"Sessions: {int(total_stats['count'])}")
    print(f"Mean total PnL: {total_stats['mean']:,.2f}")
    print(f"Std total PnL: {total_stats['std']:,.2f}")
    print(f"Median total PnL: {total_stats['p50']:,.2f}")
    print(f"5%-95% range: {total_stats['p05']:,.2f} to {total_stats['p95']:,.2f}")
    print(f"Saved Monte Carlo dashboard to {format_path(dashboard_path)}")

    if vis:
        open_monte_carlo_visualizer(dashboard_path)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "mc":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        mc_app()
    else:
        app()


if __name__ == "__main__":
    main()
