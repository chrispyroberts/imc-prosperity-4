from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import contextlib
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.error import URLError
from urllib.request import urlopen


STATE_DIR = Path.home() / ".prosperity4mcbt"
ROOT_FILE = STATE_DIR / "dashboard_root.txt"
PID_FILE = STATE_DIR / "dashboard_server.pid"
DEFAULT_PORT = 8001
STATUS_PATH = "/__prosperity4mcbt__/status.json"
RUN_DASHBOARD_PREFIX = "/__prosperity4mcbt__/runs/"


def _list_runs(current_root: Path) -> tuple[list[dict[str, object]], str | None]:
    current_root = current_root.resolve()
    runs_parent = current_root.parent
    candidates: list[Path] = []

    if runs_parent.exists():
        for child in runs_parent.iterdir():
            if child.is_dir() and (child / "dashboard.json").exists():
                candidates.append(child.resolve())

    if (current_root / "dashboard.json").exists() and current_root.resolve() not in candidates:
        candidates.append(current_root.resolve())

    candidates.sort(
        key=lambda path: (path / "dashboard.json").stat().st_mtime_ns if (path / "dashboard.json").exists() else 0,
        reverse=True,
    )

    runs: list[dict[str, object]] = []
    for run_dir in candidates:
        dashboard_path = run_dir / "dashboard.json"
        stat = dashboard_path.stat()
        runs.append(
            {
                "id": run_dir.name,
                "label": run_dir.name,
                "mtimeMs": int(stat.st_mtime_ns // 1_000_000),
                "dashboardUrl": f"{RUN_DASHBOARD_PREFIX}{run_dir.name}/dashboard.json",
            }
        )

    current_run_id = current_root.name if (current_root / "dashboard.json").exists() else (runs[0]["id"] if runs else None)
    return runs, current_run_id


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == STATUS_PATH:
            self._serve_status()
            return
        if path.startswith(RUN_DASHBOARD_PREFIX):
            self._serve_run_dashboard(path)
            return
        super().do_GET()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        return

    def _serve_status(self) -> None:
        root = Path(getattr(self, "directory", ".")).resolve()
        dashboard_path = root / "dashboard.json"
        dashboard_exists = dashboard_path.exists()
        runs, current_run_id = _list_runs(root)
        payload = {
            "root": str(root),
            "dashboardExists": dashboard_exists,
            "dashboardMtimeMs": int(dashboard_path.stat().st_mtime_ns // 1_000_000) if dashboard_exists else None,
            "dashboardSizeBytes": int(dashboard_path.stat().st_size) if dashboard_exists else None,
            "currentRunId": current_run_id,
            "runs": runs,
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_run_dashboard(self, path: str) -> None:
        root = Path(getattr(self, "directory", ".")).resolve()
        runs, _ = _list_runs(root)
        parts = [unquote(part) for part in path.split("/") if part]
        if len(parts) != 4 or parts[:2] != ["__prosperity4mcbt__", "runs"] or parts[3] != "dashboard.json":
            self.send_error(404)
            return

        run_id = parts[2]
        matching = next((run for run in runs if run["id"] == run_id), None)
        if matching is None:
            self.send_error(404)
            return

        dashboard_path = root.parent / run_id / "dashboard.json"
        if not dashboard_path.exists():
            self.send_error(404)
            return

        body = dashboard_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(root: Path, port: int = 8001) -> None:
    root = root.resolve()
    handler = partial(DashboardRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def read_root() -> Path | None:
    try:
        return Path(ROOT_FILE.read_text().strip()).resolve()
    except Exception:
        return None


def terminate_existing_server() -> None:
    pid = read_pid()
    if pid is None:
        return
    if not is_alive(pid):
        with contextlib.suppress(Exception):
            PID_FILE.unlink()
        with contextlib.suppress(Exception):
            ROOT_FILE.unlink()
        return

    with contextlib.suppress(Exception):
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 2.0
    while time.time() < deadline and is_alive(pid):
        time.sleep(0.05)
    if is_alive(pid):
        with contextlib.suppress(Exception):
            os.kill(pid, signal.SIGKILL)

    with contextlib.suppress(Exception):
        PID_FILE.unlink()
    with contextlib.suppress(Exception):
        ROOT_FILE.unlink()


def wait_for_server(port: int, timeout_seconds: float = 5.0) -> None:
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/dashboard.json"
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except URLError:
            time.sleep(0.05)
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"dashboard server did not become ready on port {port}")


def ensure_dashboard_server(root: Path, port: int = DEFAULT_PORT) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    previous_root = read_root()
    ROOT_FILE.write_text(str(root))

    current_pid = read_pid()
    if current_pid is not None and is_alive(current_pid):
        if previous_root == root:
            return
        terminate_existing_server()

    process = subprocess.Popen(
        [sys.executable, "-m", "prosperity4mcbt.dashboard_server", str(root), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(process.pid))
    wait_for_server(port)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python -m prosperity4mcbt.dashboard_server <root> [port]")

    root = Path(sys.argv[1]).resolve()
    port = int(sys.argv[2]) if len(sys.argv) == 3 else 8001
    serve_dashboard(root, port)


if __name__ == "__main__":
    main()
