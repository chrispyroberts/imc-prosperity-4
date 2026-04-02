import webbrowser
from pathlib import Path

from prosperity4mcbt.dashboard_server import ensure_dashboard_server


def open_visualizer(output_file: Path) -> None:
    raise RuntimeError(
        "The bundled frontend now only supports Monte Carlo dashboards. "
        "Use prosperity4mcbt --vis for dashboard viewing."
    )


def open_monte_carlo_visualizer(output_file: Path) -> None:
    open_dashboard(output_file)


def open_dashboard(output_file: Path) -> None:
    ensure_dashboard_server(output_file.parent)
    if output_file.name == "dashboard.json":
        webbrowser.open("http://localhost:5555/")
    else:
        webbrowser.open(f"http://localhost:5555/?open=http://localhost:8001/{output_file.name}")
