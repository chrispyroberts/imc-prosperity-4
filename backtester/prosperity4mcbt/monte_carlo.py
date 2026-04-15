from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from prosperity3bt.monte_carlo import (
    build_dashboard,
    default_dashboard_path,
    normalize_dashboard_path,
    project_root,
    resolve_actual_dir,
    rust_dir,
    GENERATED_OUTPUT_FILES,
    GENERATED_OUTPUT_DIRS,
)
import shutil


__all__ = [
    "default_dashboard_path",
    "normalize_dashboard_path",
    "run_monte_carlo_mode",
]


def run_monte_carlo_mode(
    *,
    algorithm: Path,
    dashboard_path: Path,
    data_root: Optional[Path],
    config_path: Path,
    sessions: int,
    seed: int,
    python_bin: str,
    sample_sessions: int,
    dro: bool = False,
    dro_radius: float = 2.0,
    dro_k: int = 8,
    fixed_params: bool = False,
    # legacy args (no-ops, kept for backcompat)
    fv_mode: Optional[str] = None,
    trade_mode: Optional[str] = None,
    tomato_support: Optional[str] = None,
    ticks_per_day: int = 10000,
) -> dict[str, Any]:
    output_dir = dashboard_path.parent
    if output_dir.exists():
        for name in GENERATED_OUTPUT_FILES:
            p = output_dir / name
            if p.is_file():
                p.unlink()
        for name in GENERATED_OUTPUT_DIRS:
            p = output_dir / name
            if p.is_dir():
                shutil.rmtree(p)
    output_dir.mkdir(parents=True, exist_ok=True)

    actual_dir = resolve_actual_dir(data_root)
    simulator_dir = rust_dir()
    if not simulator_dir.is_dir():
        raise RuntimeError(
            f"Rust simulator directory not found at {simulator_dir}. "
            "prosperity4mcbt currently expects a full repository checkout."
        )

    cmd = [
        "cargo", "run", "--release", "--",
        "--strategy", str(algorithm.resolve()),
        "--sessions", str(sessions),
        "--output", str(output_dir.resolve()),
        "--seed", str(seed),
        "--python-bin", python_bin,
        "--write-session-limit", str(sample_sessions),
        "--actual-dir", str(actual_dir.resolve()),
        "--ticks-per-day", str(ticks_per_day),
        "--config", str(config_path),
    ]
    if fixed_params:
        cmd.append("--fixed-params")
    if dro:
        cmd.extend(["--dro", "--dro-radius", str(dro_radius), "--dro-k", str(dro_k)])

    env = {**os.environ, "PROSPERITY4MCBT_ROOT": str(project_root().resolve())}
    subprocess.run(cmd, cwd=simulator_dir, env=env, check=True)

    dashboard = build_dashboard(
        output_dir,
        algorithm,
        sessions,
        {
            "configPath": str(config_path),
            "seed": seed,
            "sampleSessions": sample_sessions,
            "fixedParams": fixed_params,
            "dro": dro,
            "droRadius": dro_radius,
            "droK": dro_k,
        },
    )

    dro_report_path = output_dir / "dro_report.json"
    if dro_report_path.exists():
        dashboard["droReport"] = json.loads(dro_report_path.read_text())

    # embed per-product position traces from sample sidecars
    sidecar_dir = output_dir / "sample_paths"
    if sidecar_dir.exists():
        per_product_pos: dict[str, list[list]] = {}
        for sidecar_path in sorted(sidecar_dir.glob("session_*.json")):
            sidecar = json.loads(sidecar_path.read_text())
            for product, path in sidecar.get("products", {}).items():
                if product not in per_product_pos:
                    per_product_pos[product] = []
                per_product_pos[product].append({
                    "timestamps": path["timestamps"],
                    "position": path["position"],
                })
        if per_product_pos:
            dashboard["perProductPositionPaths"] = per_product_pos

    with dashboard_path.open("w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2)

    return dashboard
