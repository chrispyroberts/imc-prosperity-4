from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import contextlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


STATE_DIR = Path.home() / ".prosperity4mcbt"
ROOT_FILE = STATE_DIR / "dashboard_root.txt"
PID_FILE = STATE_DIR / "dashboard_server.pid"
DEFAULT_PORT = 8001


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        return


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
