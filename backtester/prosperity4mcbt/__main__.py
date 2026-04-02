import sys
from importlib import metadata
from pathlib import Path
from typing import Annotated, Optional

from typer import Argument, Option, Typer

from prosperity4mcbt.monte_carlo import default_dashboard_path, normalize_dashboard_path, run_monte_carlo_mode
from prosperity4mcbt.open import open_dashboard


def version_callback(value: bool) -> None:
    if value:
        try:
            version = metadata.version("prosperity4mcbt")
        except metadata.PackageNotFoundError:
            version = "0.0.0+local"
        print(f"prosperity4mcbt {version}")
        raise SystemExit(0)


app = Typer(context_settings={"help_option_names": ["--help", "-h"]})


@app.command()
def cli(
    algorithm: Annotated[
        Path,
        Argument(
            help="Path to the Python file containing the strategy to simulate.",
            show_default=False,
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    vis: Annotated[bool, Option("--vis", help="Open the Monte Carlo dashboard in the local visualizer when done.")] = False,
    out: Annotated[
        Optional[Path],
        Option(
            help="Path to dashboard JSON file (defaults to backtests/<timestamp>_monte_carlo/dashboard.json).",
            show_default=False,
            resolve_path=True,
        ),
    ] = None,
    no_out: Annotated[bool, Option("--no-out", help="Skip saving dashboard output.")] = False,
    data: Annotated[
        Optional[Path],
        Option(
            help="Path to data directory. If it contains round0/, that round0 directory is used as the actual calibration source.",
            show_default=False,
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    quick: Annotated[
        bool,
        Option("--quick", help="Preset for a fast run: 100 sessions and 10 sample sessions."),
    ] = False,
    heavy: Annotated[
        bool,
        Option("--heavy", help="Preset for a full run: 1000 sessions and 100 sample sessions."),
    ] = False,
    sessions: Annotated[int, Option("--sessions", help="Number of Monte Carlo sessions to run.")] = 1000,
    fv_mode: Annotated[str, Option("--fv-mode", help="Fair-value mode for the Rust simulator.")] = "simulate",
    trade_mode: Annotated[str, Option("--trade-mode", help="Trade-arrival mode for the Rust simulator.")] = "simulate",
    tomato_support: Annotated[str, Option("--tomato-support", help="Latent fair support for tomatoes in simulate mode.")] = "quarter",
    seed: Annotated[int, Option("--seed", help="RNG seed for the Rust simulator.")] = 20260401,
    python_bin: Annotated[
        str,
        Option("--python-bin", help="Python interpreter used for the strategy worker process."),
    ] = sys.executable,
    sample_sessions: Annotated[
        int,
        Option("--sample-sessions", help="Number of sessions to persist with full path/trace data for dashboard charts."),
    ] = 100,
    version: Annotated[
        bool,
        Option("--version", "-v", help="Show the program's version number and exit.", is_eager=True, callback=version_callback),
    ] = False,
) -> None:
    if no_out:
        print("Error: Monte Carlo mode always writes a dashboard bundle, so --no-out is not supported")
        raise SystemExit(1)
    if quick and heavy:
        print("Error: --quick and --heavy are mutually exclusive")
        raise SystemExit(1)

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
    )

    total_stats = dashboard["overall"]["totalPnl"]
    print(f"Sessions: {int(total_stats['count'])}")
    print(f"Mean total PnL: {total_stats['mean']:,.2f}")
    print(f"Std total PnL: {total_stats['std']:,.2f}")
    print(f"Median total PnL: {total_stats['p50']:,.2f}")
    print(f"5%-95% range: {total_stats['p05']:,.2f} to {total_stats['p95']:,.2f}")
    print(f"Saved Monte Carlo dashboard to {dashboard_path}")

    if vis:
        open_dashboard(dashboard_path)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
