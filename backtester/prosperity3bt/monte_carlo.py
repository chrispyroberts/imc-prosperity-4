from __future__ import annotations

import csv
import json
import math
import os
import shutil
import statistics
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DAY_OFFSETS = {-2: 0, -1: 1_000_000}
CHART_POINTS_PER_SERIES = 1500
STATIC_CHART_POINTS = 600
GENERATED_OUTPUT_FILES = {
    "dashboard.json",
    "session_summary.csv",
    "run_summary.csv",
    "run.log",
}
GENERATED_OUTPUT_DIRS = {
    "sample_paths",
    "sessions",
    "static_charts",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def rust_dir() -> Path:
    return project_root() / "rust_simulator"


def default_dashboard_path() -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path.cwd() / "backtests" / f"{timestamp}_monte_carlo" / "dashboard.json"


def normalize_dashboard_path(out: Optional[Path], no_out: bool) -> Optional[Path]:
    if no_out:
        return None

    if out is None:
        return default_dashboard_path()

    if out.suffix.lower() == ".json":
        return out

    return out / "dashboard.json"


def resolve_actual_dir(data_root: Optional[Path]) -> Path:
    if data_root is None:
        return project_root() / "data" / "round0"

    if data_root.name == "round0":
        return data_root

    round0 = data_root / "round0"
    if round0.is_dir():
        return round0

    return data_root


def quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (len(sorted_values) - 1) * q
    lo = math.floor(index)
    hi = math.ceil(index)
    if lo == hi:
        return sorted_values[lo]

    weight = index - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def downside_deviation(values: list[float]) -> float:
    downside = [min(value, 0.0) ** 2 for value in values]
    if not downside:
        return 0.0
    return math.sqrt(sum(downside) / len(downside))


def skewness(values: list[float]) -> float:
    if len(values) < 3:
        return 0.0
    mean = statistics.fmean(values)
    std = sample_std(values)
    if std == 0:
        return 0.0
    return sum(((value - mean) / std) ** 3 for value in values) / len(values)


def correlation(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) < 2:
        return 0.0
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    std_a = sample_std(a)
    std_b = sample_std(b)
    if std_a == 0 or std_b == 0:
        return 0.0
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / (len(a) - 1)
    return cov / (std_a * std_b)


def summarize_distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {}

    mean = statistics.fmean(values)
    std = sample_std(values)
    downside = downside_deviation(values)
    q05 = quantile(values, 0.05)
    q01 = quantile(values, 0.01)
    tail_5 = [value for value in values if value <= q05] or [min(values)]
    tail_1 = [value for value in values if value <= q01] or [min(values)]
    ci_half_width = 1.96 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0

    return {
        "count": float(len(values)),
        "mean": mean,
        "std": std,
        "min": min(values),
        "p01": q01,
        "p05": q05,
        "p10": quantile(values, 0.10),
        "p25": quantile(values, 0.25),
        "p50": quantile(values, 0.50),
        "p75": quantile(values, 0.75),
        "p90": quantile(values, 0.90),
        "p95": quantile(values, 0.95),
        "p99": quantile(values, 0.99),
        "max": max(values),
        "positiveRate": sum(value > 0 for value in values) / len(values),
        "negativeRate": sum(value < 0 for value in values) / len(values),
        "zeroRate": sum(value == 0 for value in values) / len(values),
        "var95": q05,
        "cvar95": statistics.fmean(tail_5),
        "var99": q01,
        "cvar99": statistics.fmean(tail_1),
        "meanConfidenceLow95": mean - ci_half_width,
        "meanConfidenceHigh95": mean + ci_half_width,
        "sharpeLike": mean / std if std > 0 else 0.0,
        "sortinoLike": mean / downside if downside > 0 else 0.0,
        "skewness": skewness(values),
    }


def histogram(values: list[float], bins: int = 40) -> dict[str, list[float] | list[int]]:
    if not values:
        return {"binEdges": [], "counts": []}

    lo = min(values)
    hi = max(values)
    if lo == hi:
        lo -= 0.5
        hi += 0.5

    width = (hi - lo) / bins
    edges = [lo + i * width for i in range(bins + 1)]
    counts = [0 for _ in range(bins)]
    for value in values:
        idx = min(int((value - lo) / width), bins - 1)
        counts[idx] += 1

    return {"binEdges": edges, "counts": counts}


def mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def normal_pdf(x: float, mu: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def fit_r_squared(actual: list[float], predicted: list[float]) -> float:
    if not actual or len(actual) != len(predicted):
        return 0.0
    actual_mean = mean(actual)
    sst = sum((value - actual_mean) ** 2 for value in actual)
    if sst <= 1e-12:
        return 0.0
    sse = sum((a - b) ** 2 for a, b in zip(actual, predicted))
    return max(0.0, 1.0 - sse / sst)


def normal_fit(values: list[float], bins: int = 40, points: int = 200) -> dict[str, Any]:
    hist = histogram(values, bins)
    bin_edges = hist["binEdges"]
    counts = hist["counts"]
    mu = mean(values)
    sigma = sample_std(values)

    if len(bin_edges) < 2:
        return {"mean": mu, "std": sigma, "r2": 0.0, "line": []}

    bin_width = float(bin_edges[1] - bin_edges[0])
    centers = [(bin_edges[index] + bin_edges[index + 1]) / 2.0 for index in range(len(counts))]
    expected_counts = [normal_pdf(center, mu, sigma) * len(values) * bin_width for center in centers]
    lo = float(bin_edges[0])
    hi = float(bin_edges[-1])
    line = []
    if points <= 1:
        points = 2
    for index in range(points):
        x = lo + (hi - lo) * index / (points - 1)
        y = normal_pdf(x, mu, sigma) * len(values) * bin_width
        line.append([x, y])

    return {
        "mean": mu,
        "std": sigma,
        "r2": fit_r_squared([float(count) for count in counts], expected_counts),
        "line": line,
    }


def linear_regression(x_values: list[float], y_values: list[float]) -> dict[str, Any]:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return {
            "slope": 0.0,
            "intercept": 0.0,
            "r2": 0.0,
            "correlation": 0.0,
            "line": [],
            "diagnosis": "insufficient data",
        }

    x_mean = mean(x_values)
    y_mean = mean(y_values)
    sxx = sum((x - x_mean) ** 2 for x in x_values)
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    slope = sxy / sxx if sxx > 1e-12 else 0.0
    intercept = y_mean - slope * x_mean
    corr = correlation(x_values, y_values)
    r2 = corr * corr
    x_min = min(x_values)
    x_max = max(x_values)
    line = [[x_min, intercept + slope * x_min], [x_max, intercept + slope * x_max]]
    strength = abs(corr)
    if strength < 0.1:
        diagnosis = "no meaningful correlation"
    elif strength < 0.3:
        diagnosis = "weak correlation"
    elif strength < 0.6:
        diagnosis = "moderate correlation"
    else:
        diagnosis = "strong correlation"

    return {
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "correlation": corr,
        "line": line,
        "diagnosis": diagnosis,
    }


def read_csv_dicts(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def downsample_indices(length: int, max_points: int) -> list[int]:
    if length <= max_points:
        return list(range(length))

    if max_points <= 1:
        return [length - 1]

    indices = [min(round(i * (length - 1) / (max_points - 1)), length - 1) for i in range(max_points)]
    deduped: list[int] = []
    seen: set[int] = set()
    for index in indices:
        if index not in seen:
            deduped.append(index)
            seen.add(index)
    if deduped[-1] != length - 1:
        deduped[-1] = length - 1
    return deduped


def downsample_path_node(node: dict[str, list[float] | list[int]], max_points: int) -> dict[str, list[float] | list[int]]:
    indices = downsample_indices(len(node["timestamps"]), max_points)
    return {key: [values[index] for index in indices] for key, values in node.items()}


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )



def _col(row: dict, *keys: str, default: float = 0.0) -> float:
    """Return float from first matching key; fall back to default."""
    for k in keys:
        if k in row:
            v = row[k]
            return float(v) if v not in ("", None) else default
    return default


def _icol(row: dict, *keys: str, default: int = 0) -> int:
    """Return int from first matching key; fall back to default."""
    for k in keys:
        if k in row:
            v = row[k]
            return int(v) if v not in ("", None) else default
    return default


def _detect_product_names(row: dict[str, str]) -> list[str]:
    """Detect product names from CSV row keys by finding {NAME}_pnl columns."""
    names = []
    for key in row:
        if key.endswith("_pnl") and not key.startswith("total"):
            names.append(key[: -len("_pnl")])
    return sorted(names)


def load_session_summaries(output_dir: Path) -> list[dict[str, Any]]:
    rows = read_csv_dicts(output_dir / "session_summary.csv", ",")
    parsed = []
    product_names: list[str] = _detect_product_names(rows[0]) if rows else []
    for row in rows:
        entry: dict[str, Any] = {
            "sessionId": int(row["session_id"]),
            "totalPnl": float(row["total_pnl"]),
            "emeraldPnl": _col(row, "EMERALDS_pnl", "emerald_pnl"),
            "tomatoPnl": _col(row, "TOMATOES_pnl", "tomato_pnl"),
            "emeraldPosition": _icol(row, "EMERALDS_position", "emerald_position"),
            "tomatoPosition": _icol(row, "TOMATOES_position", "tomato_position"),
            "emeraldCash": _col(row, "EMERALDS_cash", "emerald_cash"),
            "tomatoCash": _col(row, "TOMATOES_cash", "tomato_cash"),
            "totalSlopePerStep": _col(row, "total_slope_per_step"),
            "totalR2": _col(row, "total_r2"),
            "emeraldSlopePerStep": _col(row, "EMERALDS_slope_per_step", "emerald_slope_per_step"),
            "emeraldR2": _col(row, "EMERALDS_r2", "emerald_r2"),
            "tomatoSlopePerStep": _col(row, "TOMATOES_slope_per_step", "tomato_slope_per_step"),
            "tomatoR2": _col(row, "TOMATOES_r2", "tomato_r2"),
            # dynamic per-product dicts for frontend iteration
            "perProductPnl": {n: _col(row, f"{n}_pnl") for n in product_names},
            "perProductPosition": {n: _icol(row, f"{n}_position") for n in product_names},
            "perProductCash": {n: _col(row, f"{n}_cash") for n in product_names},
            "perProductSlopePerStep": {n: _col(row, f"{n}_slope_per_step") for n in product_names},
            "perProductR2": {n: _col(row, f"{n}_r2") for n in product_names},
        }
        parsed.append(entry)
    return parsed


def load_run_summaries(output_dir: Path) -> list[dict[str, Any]]:
    rows = read_csv_dicts(output_dir / "run_summary.csv", ",")
    parsed = []
    product_names: list[str] = _detect_product_names(rows[0]) if rows else []
    for row in rows:
        entry: dict[str, Any] = {
            "sessionId": int(row["session_id"]),
            "day": int(row["day"]),
            "totalPnl": float(row["total_pnl"]),
            "emeraldPnl": _col(row, "EMERALDS_pnl", "emerald_pnl"),
            "tomatoPnl": _col(row, "TOMATOES_pnl", "tomato_pnl"),
            "totalSlopePerStep": _col(row, "total_slope_per_step"),
            "totalR2": _col(row, "total_r2"),
            "emeraldSlopePerStep": _col(row, "EMERALDS_slope_per_step", "emerald_slope_per_step"),
            "emeraldR2": _col(row, "EMERALDS_r2", "emerald_r2"),
            "tomatoSlopePerStep": _col(row, "TOMATOES_slope_per_step", "tomato_slope_per_step"),
            "tomatoR2": _col(row, "TOMATOES_r2", "tomato_r2"),
            # dynamic per-product dicts
            "perProductPnl": {n: _col(row, f"{n}_pnl") for n in product_names},
            "perProductSlopePerStep": {n: _col(row, f"{n}_slope_per_step") for n in product_names},
            "perProductR2": {n: _col(row, f"{n}_r2") for n in product_names},
        }
        parsed.append(entry)
    return parsed


def load_sample_session(session_dir: Path) -> dict[str, Any]:
    round_dir = session_dir / "round0"
    traces_by_product: dict[str, dict[str, list[float]]] = {}
    prices_by_product: dict[str, dict[str, list[float]]] = {}
    day_files = sorted(
        int(path.stem.split("_")[-1])
        for path in round_dir.glob("trace_round_0_day_*.csv")
    )

    for day_index, day in enumerate(day_files):
        trace_rows = read_csv_dicts(round_dir / f"trace_round_0_day_{day}.csv", ";")
        price_rows = read_csv_dicts(round_dir / f"prices_round_0_day_{day}.csv", ";")

        for row in trace_rows:
            product = row["product"]
            if product not in traces_by_product:
                traces_by_product[product] = {
                    "timestamps": [],
                    "fair": [],
                    "position": [],
                    "cash": [],
                    "mtmPnl": [],
                }
            ts = day_index * 1_000_000 + int(row["timestamp"])
            traces_by_product[product]["timestamps"].append(ts)
            traces_by_product[product]["fair"].append(float(row["fair_value"]))
            traces_by_product[product]["position"].append(int(row["position"]))
            traces_by_product[product]["cash"].append(float(row["cash"]))
            traces_by_product[product]["mtmPnl"].append(float(row["mtm_pnl"]))

        for row in price_rows:
            product = row["product"]
            if product not in prices_by_product:
                prices_by_product[product] = {
                    "timestamps": [],
                    "mid": [],
                    "bid1": [],
                    "ask1": [],
                }
            ts = day_index * 1_000_000 + int(row["timestamp"])
            prices_by_product[product]["timestamps"].append(ts)
            prices_by_product[product]["mid"].append(float(row["mid_price"]))
            prices_by_product[product]["bid1"].append(
                float(row["bid_price_1"]) if row["bid_price_1"] not in ("", None) else math.nan
            )
            prices_by_product[product]["ask1"].append(
                float(row["ask_price_1"]) if row["ask_price_1"] not in ("", None) else math.nan
            )

    products = {}
    for product, trace in traces_by_product.items():
        price = prices_by_product.get(product, {"mid": [], "bid1": [], "ask1": []})
        products[product] = {
            "timestamps": trace["timestamps"],
            "fair": trace["fair"],
            "mid": price["mid"],
            "bid1": price["bid1"],
            "ask1": price["ask1"],
            "position": trace["position"],
            "cash": trace["cash"],
            "mtmPnl": trace["mtmPnl"],
        }

    if not products:
        timestamps = []
        total_pnl = []
    else:
        first_product = next(iter(products))
        timestamps = products[first_product]["timestamps"]
        total_pnl = []
        for idx in range(len(timestamps)):
            total_pnl.append(sum(products[product]["mtmPnl"][idx] for product in products))

    return {
        "sessionId": int(session_dir.name.split("_")[-1]),
        "products": products,
        "total": {
            "timestamps": timestamps,
            "mtmPnl": total_pnl,
        },
    }


def sampled_chart_path(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "sessionId": sample["sessionId"],
        "products": {
            product: downsample_path_node(node, CHART_POINTS_PER_SERIES)
            for product, node in sample["products"].items()
        },
        "total": downsample_path_node(sample["total"], CHART_POINTS_PER_SERIES),
    }


def write_sample_path_sidecars(output_dir: Path, sample_session_dirs: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    sampled_paths: list[dict[str, Any]] = []
    sidecar_dir = output_dir / "sample_paths"
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    for session_dir in sample_session_dirs:
        sample = load_sample_session(session_dir)
        sampled = sampled_chart_path(sample)
        sampled_paths.append(sampled)
        relative_path = Path("sample_paths") / f"{session_dir.name}.json"
        sidecar_path = output_dir / relative_path
        with sidecar_path.open("w", encoding="utf-8") as handle:
            json.dump(sampled, handle, separators=(",", ":"))
        refs.append(
            {
                "sessionId": sampled["sessionId"],
                "url": relative_path.as_posix(),
            }
        )

    return refs, sampled_paths


def quantile_series(sample_paths: list[dict[str, Any]], value_getter) -> dict[str, list[float]]:
    if not sample_paths:
        return {}

    base_values = value_getter(sample_paths[0])
    indices = downsample_indices(len(base_values), STATIC_CHART_POINTS)
    timestamps = [sample_paths[0]["total"]["timestamps"][index] for index in indices]

    p05: list[float] = []
    p25: list[float] = []
    p50: list[float] = []
    p75: list[float] = []
    p95: list[float] = []
    mean: list[float] = []

    for index in indices:
        values = [value_getter(path)[index] for path in sample_paths]
        p05.append(quantile(values, 0.05))
        p25.append(quantile(values, 0.25))
        p50.append(quantile(values, 0.50))
        p75.append(quantile(values, 0.75))
        p95.append(quantile(values, 0.95))
        mean.append(statistics.fmean(values))

    return {
        "timestamps": timestamps,
        "p05": p05,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p95": p95,
        "mean": mean,
    }


def mean_std_band_series(sample_paths: list[dict[str, Any]], value_getter) -> dict[str, list[float]]:
    if not sample_paths:
        return {}

    base_values = value_getter(sample_paths[0])
    indices = downsample_indices(len(base_values), STATIC_CHART_POINTS)
    timestamps = [sample_paths[0]["total"]["timestamps"][index] for index in indices]

    mean_values: list[float] = []
    std1_low: list[float] = []
    std1_high: list[float] = []
    std3_low: list[float] = []
    std3_high: list[float] = []

    for index in indices:
        values = [value_getter(path)[index] for path in sample_paths]
        mu = statistics.fmean(values)
        sigma = sample_std(values)
        mean_values.append(mu)
        std1_low.append(mu - sigma)
        std1_high.append(mu + sigma)
        std3_low.append(mu - 3.0 * sigma)
        std3_high.append(mu + 3.0 * sigma)

    return {
        "timestamps": timestamps,
        "mean": mean_values,
        "std1Low": std1_low,
        "std1High": std1_high,
        "std3Low": std3_low,
        "std3High": std3_high,
    }


def overlay_series(sample_paths: list[dict[str, Any]], value_getter, overlay_count: int = 10) -> dict[str, Any]:
    overlays = []
    for path in sample_paths[:overlay_count]:
        values = value_getter(path)
        indices = downsample_indices(len(values), STATIC_CHART_POINTS)
        overlays.append(
            {
                "sessionId": path["sessionId"],
                "timestamps": [path["total"]["timestamps"][index] for index in indices],
                "values": [values[index] for index in indices],
            }
        )
    return {"overlays": overlays}


def path_chart_svg(
    title: str,
    subtitle: str,
    timestamps: list[float],
    bands: dict[str, list[float]],
    overlays: list[dict[str, Any]] | None = None,
) -> str:
    width = 1200
    height = 420
    left = 64
    right = 24
    top = 56
    bottom = 36
    plot_width = width - left - right
    plot_height = height - top - bottom

    y_values = bands["p05"] + bands["p95"] + bands["mean"]
    if overlays:
        for overlay in overlays:
            y_values.extend(overlay["values"])
    y_min = min(y_values)
    y_max = max(y_values)
    if y_min == y_max:
        y_min -= 1.0
        y_max += 1.0

    x_min = timestamps[0]
    x_max = timestamps[-1]
    x_range = x_max - x_min if x_max != x_min else 1.0
    y_range = y_max - y_min

    def x_pos(ts: float) -> float:
        return left + (ts - x_min) / x_range * plot_width

    def y_pos(value: float) -> float:
        return top + (1.0 - (value - y_min) / y_range) * plot_height

    def polyline(ts_values: list[float], values: list[float]) -> str:
        return " ".join(f"{x_pos(ts):.2f},{y_pos(value):.2f}" for ts, value in zip(ts_values, values))

    def band_polygon(lower: list[float], upper: list[float]) -> str:
        forward = [f"{x_pos(ts):.2f},{y_pos(value):.2f}" for ts, value in zip(timestamps, upper)]
        backward = [f"{x_pos(ts):.2f},{y_pos(value):.2f}" for ts, value in zip(reversed(timestamps), reversed(lower))]
        return " ".join(forward + backward)

    tick_labels = [timestamps[0], timestamps[len(timestamps) // 2], timestamps[-1]]
    y_ticks = [y_min, (y_min + y_max) / 2.0, y_max]

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#101113"/>',
        f'<text x="{left}" y="28" fill="#f3f4f6" font-size="22" font-family="system-ui, sans-serif">{svg_escape(title)}</text>',
        f'<text x="{left}" y="46" fill="#9ca3af" font-size="13" font-family="system-ui, sans-serif">{svg_escape(subtitle)}</text>',
        f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#141517" stroke="#2c2e33"/>',
    ]

    for tick in y_ticks:
        y = y_pos(tick)
        svg_parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#25262b" stroke-width="1"/>')
        svg_parts.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" fill="#9ca3af" font-size="12" text-anchor="end" font-family="system-ui, sans-serif">{tick:.2f}</text>'
        )

    for tick in tick_labels:
        x = x_pos(tick)
        svg_parts.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_height}" stroke="#25262b" stroke-width="1"/>')
        svg_parts.append(
            f'<text x="{x:.2f}" y="{top + plot_height + 18}" fill="#9ca3af" font-size="12" text-anchor="middle" font-family="system-ui, sans-serif">{int(tick)}</text>'
        )

    svg_parts.append(f'<polygon points="{band_polygon(bands["p05"], bands["p95"])}" fill="#60a5fa" opacity="0.18"/>')
    svg_parts.append(f'<polygon points="{band_polygon(bands["p25"], bands["p75"])}" fill="#3b82f6" opacity="0.28"/>')
    svg_parts.append(f'<polyline points="{polyline(timestamps, bands["p50"])}" fill="none" stroke="#f8fafc" stroke-width="2"/>')
    svg_parts.append(f'<polyline points="{polyline(timestamps, bands["mean"])}" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="6 4"/>')

    if overlays:
        for overlay in overlays:
            svg_parts.append(
                f'<polyline points="{polyline(overlay["timestamps"], overlay["values"])}" fill="none" stroke="#34d399" stroke-width="1.1" opacity="0.24"/>'
            )

    legend_x = left + 12
    legend_y = top + 18
    svg_parts.extend(
        [
            f'<rect x="{legend_x}" y="{legend_y - 10}" width="16" height="10" fill="#60a5fa" opacity="0.18"/>',
            f'<text x="{legend_x + 22}" y="{legend_y}" fill="#d1d5db" font-size="12" font-family="system-ui, sans-serif">P05-P95</text>',
            f'<rect x="{legend_x + 96}" y="{legend_y - 10}" width="16" height="10" fill="#3b82f6" opacity="0.28"/>',
            f'<text x="{legend_x + 118}" y="{legend_y}" fill="#d1d5db" font-size="12" font-family="system-ui, sans-serif">P25-P75</text>',
            f'<line x1="{legend_x + 194}" y1="{legend_y - 5}" x2="{legend_x + 210}" y2="{legend_y - 5}" stroke="#f8fafc" stroke-width="2"/>',
            f'<text x="{legend_x + 216}" y="{legend_y}" fill="#d1d5db" font-size="12" font-family="system-ui, sans-serif">Median</text>',
            f'<line x1="{legend_x + 278}" y1="{legend_y - 5}" x2="{legend_x + 294}" y2="{legend_y - 5}" stroke="#f59e0b" stroke-width="2" stroke-dasharray="6 4"/>',
            f'<text x="{legend_x + 300}" y="{legend_y}" fill="#d1d5db" font-size="12" font-family="system-ui, sans-serif">Mean</text>',
        ]
    )

    svg_parts.append("</svg>")
    return "".join(svg_parts)


def write_static_chart_svgs(output_dir: Path, sampled_paths: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    if not sampled_paths:
        return {}

    charts_dir = output_dir / "static_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    # build specs dynamically per product seen in the first sampled path
    product_names = list(sampled_paths[0].get("products", {}).keys())
    chart_specs = {
        product: [
            ("fair_bands", "Fair Price Bands",
             lambda path, p=product: path["products"][p]["fair"]),
            ("mtm_bands", "MTM PnL Bands",
             lambda path, p=product: path["products"][p]["mtmPnl"]),
            ("position_bands", "Position Bands",
             lambda path, p=product: path["products"][p]["position"]),
        ]
        for product in product_names
    }

    refs: dict[str, list[dict[str, str]]] = {}
    for product, specs in chart_specs.items():
        product_refs: list[dict[str, str]] = []
        product_dir = charts_dir / product.lower()
        product_dir.mkdir(parents=True, exist_ok=True)
        for slug, title, getter in specs:
            bands = quantile_series(sampled_paths, getter)
            overlays = overlay_series(sampled_paths, getter)["overlays"]
            svg = path_chart_svg(
                title=f"{product} {title}",
                subtitle=f"{len(sampled_paths)} persisted session traces • overlays show first {min(10, len(overlays))} sessions",
                timestamps=bands["timestamps"],
                bands=bands,
                overlays=overlays,
            )
            relative_path = Path("static_charts") / product.lower() / f"{slug}.svg"
            chart_path = output_dir / relative_path
            chart_path.write_text(svg, encoding="utf-8")
            product_refs.append({"title": title, "url": relative_path.as_posix()})
        refs[product] = product_refs

    return refs


def build_band_series(sampled_paths: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, list[float]]]]:
    if not sampled_paths:
        return {}

    product_names = list(sampled_paths[0].get("products", {}).keys())
    return {
        product: {
            "fair": mean_std_band_series(sampled_paths, lambda path, p=product: path["products"][p]["fair"]),
            "mtmPnl": mean_std_band_series(sampled_paths, lambda path, p=product: path["products"][p]["mtmPnl"]),
            "position": mean_std_band_series(sampled_paths, lambda path, p=product: path["products"][p]["position"]),
        }
        for product in product_names
    }


def _compute_fv_bands(
    sampled_paths: list[dict[str, Any]],
    product_names: list[str],
) -> dict[str, dict[str, list[float]]]:
    """compute p05/p50/p95 FV bands per product across sample sessions."""
    result: dict[str, dict[str, list[float]]] = {}
    for product in product_names:
        paths_with_product = [p for p in sampled_paths if product in p.get("products", {})]
        if not paths_with_product:
            continue
        base = paths_with_product[0]["products"][product]["fair"]
        indices = downsample_indices(len(base), STATIC_CHART_POINTS)
        timestamps = [paths_with_product[0]["total"]["timestamps"][i] for i in indices]
        band_p05: list[float] = []
        band_p50: list[float] = []
        band_p95: list[float] = []
        for i in indices:
            vals = [p["products"][product]["fair"][i] for p in paths_with_product]
            band_p05.append(quantile(vals, 0.05))
            band_p50.append(quantile(vals, 0.50))
            band_p95.append(quantile(vals, 0.95))
        result[product] = {
            "timestamps": timestamps,
            "band_p05": band_p05,
            "band_p50": band_p50,
            "band_p95": band_p95,
        }
    return result


def _load_observed_fv(product_names: list[str]) -> dict[str, dict[str, list[float]]]:
    """load observed day-0 FV from calibration data files if present."""
    data_dir = project_root() / "calibration" / "round1" / "data"
    observed: dict[str, dict[str, list[float]]] = {}
    for product in product_names:
        slug = product.lower().replace(" ", "_")
        path = data_dir / f"fv_and_book_{slug}.json"
        if not path.exists():
            continue
        fb = json.loads(path.read_text(encoding="utf-8"))
        ticks = fb.get("ticks", [])
        observed[product] = {
            "timestamps": [t["timestamp"] for t in ticks],
            "fv": [t["fv"] for t in ticks],
        }
    return observed


def build_dashboard(output_dir: Path, algorithm: Path, sessions: int, config: dict[str, Any]) -> dict[str, Any]:
    session_rows = load_session_summaries(output_dir)
    run_rows = load_run_summaries(output_dir)
    total = [row["totalPnl"] for row in session_rows]
    emerald = [row["emeraldPnl"] for row in session_rows]
    tomato = [row["tomatoPnl"] for row in session_rows]
    emerald_pos = [row["emeraldPosition"] for row in session_rows]
    tomato_pos = [row["tomatoPosition"] for row in session_rows]
    emerald_cash = [row["emeraldCash"] for row in session_rows]
    tomato_cash = [row["tomatoCash"] for row in session_rows]
    total_profitability = [row["totalSlopePerStep"] for row in run_rows]
    total_stability = [row["totalR2"] for row in run_rows]
    emerald_profitability = [row["emeraldSlopePerStep"] for row in run_rows]
    emerald_stability = [row["emeraldR2"] for row in run_rows]
    tomato_profitability = [row["tomatoSlopePerStep"] for row in run_rows]
    tomato_stability = [row["tomatoR2"] for row in run_rows]
    session_total_profitability = [row["totalSlopePerStep"] for row in session_rows]
    session_total_stability = [row["totalR2"] for row in session_rows]
    session_emerald_profitability = [row["emeraldSlopePerStep"] for row in session_rows]
    session_emerald_stability = [row["emeraldR2"] for row in session_rows]
    session_tomato_profitability = [row["tomatoSlopePerStep"] for row in session_rows]
    session_tomato_stability = [row["tomatoR2"] for row in session_rows]

    # detect product names dynamically from session rows
    product_names: list[str] = sorted(session_rows[0].get("perProductPnl", {}).keys()) if session_rows else []

    sample_session_dirs = sorted((output_dir / "sessions").glob("session_*")) if (output_dir / "sessions").exists() else []
    sample_path_refs, sampled_paths = write_sample_path_sidecars(output_dir, sample_session_dirs) if sample_session_dirs else ([], [])
    band_chart_refs = write_static_chart_svgs(output_dir, sampled_paths) if sampled_paths else {}
    band_series = build_band_series(sampled_paths) if sampled_paths else {}
    per_product_fv_bands = _compute_fv_bands(sampled_paths, product_names) if sampled_paths else {}
    per_product_observed_fv = _load_observed_fv(product_names)

    runs_by_session: dict[int, list[dict[str, Any]]] = {}
    for run in run_rows:
        runs_by_session.setdefault(run["sessionId"], []).append(run)
    for row in session_rows:
        session_runs = runs_by_session.get(row["sessionId"], [])
        if session_runs:
            row["runMeanTotalSlopePerStep"] = statistics.fmean(run["totalSlopePerStep"] for run in session_runs)
            row["runMeanTotalR2"] = statistics.fmean(run["totalR2"] for run in session_runs)
        else:
            row["runMeanTotalSlopePerStep"] = row["totalSlopePerStep"]
            row["runMeanTotalR2"] = row["totalR2"]

    top_sessions = sorted(session_rows, key=lambda row: row["totalPnl"], reverse=True)[:10]
    bottom_sessions = sorted(session_rows, key=lambda row: row["totalPnl"])[:10]
    scatter_fit = linear_regression(emerald, tomato)
    total_normal_fit = normal_fit(total)
    emerald_normal_fit = normal_fit(emerald)
    tomato_normal_fit = normal_fit(tomato)

    # per-product histogram and normal-fit dicts keyed by product name
    per_product_pnl_lists = {
        n: [row["perProductPnl"].get(n, 0.0) for row in session_rows] for n in product_names
    }
    per_product_profitability_lists = {
        n: [row["perProductSlopePerStep"].get(n, 0.0) for row in run_rows] for n in product_names
    }
    per_product_stability_lists = {
        n: [row["perProductR2"].get(n, 0.0) for row in run_rows] for n in product_names
    }
    per_product_histograms = {
        n: {
            "pnl": histogram(per_product_pnl_lists[n]),
            "profitability": histogram(per_product_profitability_lists[n]),
            "stability": histogram(per_product_stability_lists[n]),
        }
        for n in product_names
    }
    per_product_normal_fits = {
        n: normal_fit(per_product_pnl_lists[n]) for n in product_names
    }
    per_product_trend_fits = {
        n: {
            "profitability": summarize_distribution(per_product_profitability_lists[n]),
            "stability": summarize_distribution(per_product_stability_lists[n]),
        }
        for n in product_names
    }

    # per-product stats for products dict (dynamic, replaces hardcoded EMERALDS/TOMATOES)
    per_product_position_lists = {
        n: [float(row["perProductPosition"].get(n, 0)) for row in session_rows] for n in product_names
    }
    per_product_cash_lists = {
        n: [row["perProductCash"].get(n, 0.0) for row in session_rows] for n in product_names
    }
    products_stats = {
        n: {
            "pnl": summarize_distribution(per_product_pnl_lists[n]),
            "finalPosition": summarize_distribution(per_product_position_lists[n]),
            "cash": summarize_distribution(per_product_cash_lists[n]),
        }
        for n in product_names
    }

    return {
        "kind": "monte_carlo_dashboard",
        "meta": {
            "algorithmPath": str(algorithm),
            "sessionCount": sessions,
            "bandSessionCount": len(sample_session_dirs),
            **config,
        },
        "productNames": product_names,
        "overall": {
            "totalPnl": summarize_distribution(total),
            "emeraldPnl": summarize_distribution(emerald),
            "tomatoPnl": summarize_distribution(tomato),
            "emeraldTomatoCorrelation": correlation(emerald, tomato),
        },
        "trendFits": {
            "TOTAL": {
                "profitability": summarize_distribution(total_profitability),
                "stability": summarize_distribution(total_stability),
            },
            "EMERALDS": {
                "profitability": summarize_distribution(emerald_profitability),
                "stability": summarize_distribution(emerald_stability),
            },
            "TOMATOES": {
                "profitability": summarize_distribution(tomato_profitability),
                "stability": summarize_distribution(tomato_stability),
            },
            **per_product_trend_fits,
        },
        "aggregateTrendFits": {
            "TOTAL": {
                "profitability": summarize_distribution(session_total_profitability),
                "stability": summarize_distribution(session_total_stability),
            },
            "EMERALDS": {
                "profitability": summarize_distribution(session_emerald_profitability),
                "stability": summarize_distribution(session_emerald_stability),
            },
            "TOMATOES": {
                "profitability": summarize_distribution(session_tomato_profitability),
                "stability": summarize_distribution(session_tomato_stability),
            },
        },
        "normalFits": {
            "totalPnl": total_normal_fit,
            "emeraldPnl": emerald_normal_fit,
            "tomatoPnl": tomato_normal_fit,
        },
        "scatterFit": scatter_fit,
        "generatorModel": {
            "EMERALDS": {
                "name": "Fixed Fair Value",
                "formula": "F_t = 10000",
                "notes": [
                    "No stochastic component",
                    "Bots quote directly around the fixed fair value",
                ],
            },
            "TOMATOES": {
                "name": "Latent Fair Random Walk",
                "formula": "x_{t+1} = x_t + ε_t",
                "notes": [
                    "Zero-drift latent fair process used by the quoting bots",
                    "Visible book states emerge after deterministic quote rounding",
                ],
            },
        },
        "products": products_stats,
        "perProductHistograms": per_product_histograms,
        "perProductNormalFits": per_product_normal_fits,
        "histograms": {
            "totalPnl": histogram(total),
            "emeraldPnl": histogram(emerald),
            "tomatoPnl": histogram(tomato),
            "totalProfitability": histogram(total_profitability),
            "totalStability": histogram(total_stability),
            "emeraldProfitability": histogram(emerald_profitability),
            "emeraldStability": histogram(emerald_stability),
            "tomatoProfitability": histogram(tomato_profitability),
            "tomatoStability": histogram(tomato_stability),
        },
        "sessions": session_rows,
        "runs": run_rows,
        "topSessions": top_sessions,
        "bottomSessions": bottom_sessions,
        "samplePaths": [],
        "samplePathRefs": sample_path_refs,
        "bandChartRefs": band_chart_refs,
        "bandSeries": band_series,
        "perProductFvBands": per_product_fv_bands,
        "perProductObservedFv": per_product_observed_fv,
    }


def run_rust_monte_carlo(
    algorithm: Path,
    output_dir: Path,
    data_root: Optional[Path],
    sessions: int,
    fv_mode: str,
    trade_mode: str,
    tomato_support: str,
    seed: int,
    python_bin: str,
    sample_sessions: int,
    ticks_per_day: int = 10000,
) -> None:
    actual_dir = resolve_actual_dir(data_root)
    simulator_dir = rust_dir()
    if not simulator_dir.is_dir():
        raise RuntimeError(
            f"Rust simulator directory not found at {simulator_dir}. "
            "prosperity4mcbt currently expects a full repository checkout."
        )
    cmd = [
        "cargo",
        "run",
        "--release",
        "--",
        "--strategy",
        str(algorithm.resolve()),
        "--sessions",
        str(sessions),
        "--output",
        str(output_dir.resolve()),
        "--fv-mode",
        fv_mode,
        "--trade-mode",
        trade_mode,
        "--seed",
        str(seed),
        "--python-bin",
        python_bin,
        "--write-session-limit",
        str(sample_sessions),
        "--actual-dir",
        str(actual_dir.resolve()),
        "--ticks-per-day",
        str(ticks_per_day),
    ]
    env = {**os.environ, "PROSPERITY4MCBT_ROOT": str(project_root().resolve())}
    subprocess.run(cmd, cwd=simulator_dir, env=env, check=True)


def run_monte_carlo_mode(
    algorithm: Path,
    dashboard_path: Path,
    data_root: Optional[Path],
    sessions: int,
    fv_mode: str,
    trade_mode: str,
    tomato_support: str,
    seed: int,
    python_bin: str,
    sample_sessions: int,
    ticks_per_day: int = 10000,
) -> dict[str, Any]:
    output_dir = dashboard_path.parent
    if output_dir.exists():
        for name in GENERATED_OUTPUT_FILES:
            path = output_dir / name
            if path.is_file():
                path.unlink()
        for name in GENERATED_OUTPUT_DIRS:
            path = output_dir / name
            if path.is_dir():
                shutil.rmtree(path)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_rust_monte_carlo(
        algorithm=algorithm,
        output_dir=output_dir,
        data_root=data_root,
        sessions=sessions,
        fv_mode=fv_mode,
        trade_mode=trade_mode,
        tomato_support=tomato_support,
        seed=seed,
        python_bin=python_bin,
        sample_sessions=sample_sessions,
        ticks_per_day=ticks_per_day,
    )

    dashboard = build_dashboard(
        output_dir,
        algorithm,
        sessions,
        {
            "fvMode": fv_mode,
            "tradeMode": trade_mode,
            "tomatoSupport": tomato_support,
            "seed": seed,
            "sampleSessions": sample_sessions,
        },
    )
    with dashboard_path.open("w", encoding="utf-8") as handle:
        json.dump(dashboard, handle, indent=2)

    return dashboard
