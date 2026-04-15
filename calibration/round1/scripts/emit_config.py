"""Consolidate per-product calibration artifacts into configs/round1.toml."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


# --- posterior helpers ---

def _parse_stat(v: Any) -> tuple[float, float]:
    """Return (mean, std) regardless of whether v is [m,s] or {"mean":m,"std":s}."""
    if isinstance(v, (list, tuple)):
        return float(v[0]), float(v[1])
    return float(v["mean"]), float(v["std"])


def _dist(mean: float, std: float) -> str:
    """Emit a scalar or normal/lognormal distribution inline table string."""
    if std < 1e-12 or std / max(abs(mean), 1e-12) < 1e-4:
        return f"{mean}"
    return f'{{ dist = "normal", mean = {mean}, std = {std} }}'


def _dist_sigma(mean: float, std: float) -> str:
    """For strictly-positive sigma params prefer lognormal (delta-method)."""
    if mean < 1e-9 or std < 1e-12:
        return f"{mean}"
    rel = std / mean
    if rel < 1e-4:
        return f"{mean}"
    # lognormal: mu = log(mean) - 0.5*log(1 + rel^2), sigma_ln = sqrt(log(1 + rel^2))
    sigma_ln = math.sqrt(math.log(1.0 + rel * rel))
    mu_ln = math.log(mean) - 0.5 * sigma_ln ** 2
    return f'{{ dist = "lognormal", mu = {mu_ln:.6f}, sigma = {sigma_ln:.6f} }}'


def _uniform_int(lo: int, hi: int) -> str:
    return f'{{ dist = "uniform_int", lo = {lo}, hi = {hi} }}'


def _beta(alpha: float, beta: float) -> str:
    return f'{{ dist = "beta", alpha = {alpha}, beta = {beta} }}'


# --- fv_process section ---

def _fv_lines(fit: dict) -> list[str]:
    model = fit["model"]
    posterior = fit["posterior"]
    lines = [f'model = "{model}"']
    if model == "mean_revert_ou":
        c_m, c_s = _parse_stat(posterior["center"])
        k_m, k_s = _parse_stat(posterior["kappa"])
        s_m, s_s = _parse_stat(posterior["sigma"])
        lines.append(f"center = {_dist(c_m, c_s)}")
        lines.append(f"kappa  = {_dist_sigma(k_m, k_s)}")
        lines.append(f"sigma  = {_dist_sigma(s_m, s_s)}")
    elif model == "drifting_walk":
        i_m, i_s = _parse_stat(posterior["initial"])
        d_m, d_s = _parse_stat(posterior["drift"])
        s_m, s_s = _parse_stat(posterior["sigma"])
        lines.append(f"initial = {_dist(i_m, i_s)}")
        lines.append(f"drift   = {_dist(d_m, d_s)}")
        lines.append(f"sigma   = {_dist_sigma(s_m, s_s)}")
    elif model == "fixed":
        p_m, p_s = _parse_stat(posterior["price"])
        lines.append(f"price = {_dist(p_m, p_s)}")
    else:
        raise ValueError(f"unknown fv model: {model}")
    return lines


# --- bot sections ---

def _bot1_lines(b: dict) -> list[str]:
    vol = _uniform_int(int(b["volume_lo"]), int(b["volume_hi"]))
    pr = b.get("presence_rate", 1.0)
    lines = [
        f'bid_rule = "{b["bid_rule"]}"',
        f'ask_rule = "{b["ask_rule"]}"',
        f"offset   = {float(b['offset'])}",
        f"volume   = {vol}",
    ]
    if abs(float(pr) - 1.0) > 1e-9:
        lines.append(f"presence_rate = {float(pr)}")
    return lines


def _bot2_lines(b: dict) -> list[str]:
    vol = _uniform_int(int(b["volume_lo"]), int(b["volume_hi"]))
    pr = b.get("presence_rate", 1.0)
    lines = [
        f'bid_rule = "{b["bid_rule"]}"',
        f'ask_rule = "{b["ask_rule"]}"',
        f"offset   = {float(b['offset'])}",
        f"volume   = {vol}",
    ]
    if abs(float(pr) - 1.0) > 1e-9:
        lines.append(f"presence_rate = {float(pr)}")
    return lines


def _bot3_lines(b: dict) -> list[str]:
    alpha, beta_v = b["presence_rate_beta"]
    cx_lo, cx_hi = b["crossing_volume"]
    pa_lo, pa_hi = b["passive_volume"]
    support = b["price_delta_support"]
    support_str = "[" + ", ".join(str(x) for x in support) + "]"
    return [
        f"presence_rate       = {_beta(alpha, beta_v)}",
        f"side_bid_prob       = {float(b['side_bid_prob'])}",
        f"price_delta_support = {support_str}",
        f"crossing_volume     = {_uniform_int(int(cx_lo), int(cx_hi))}",
        f"passive_volume      = {_uniform_int(int(pa_lo), int(pa_hi))}",
    ]


def _taker_lines(t: dict) -> list[str]:
    ta_a, ta_b = t["trade_active_beta"]
    st_a, st_b = t["second_trade_beta"]
    bp_a, bp_b = t["buy_prob_beta"]
    return [
        f"trade_active_prob = {_beta(ta_a, ta_b)}",
        f"second_trade_prob = {_beta(st_a, st_b)}",
        f"buy_prob          = {_beta(bp_a, bp_b)}",
    ]


# --- product block ---

def _product_block(name: str, position_limit: int, fit: dict, bots: dict) -> str:
    lines: list[str] = []
    lines.append(f"[[products]]")
    lines.append(f'name = "{name}"')
    lines.append(f"position_limit = {position_limit}")
    lines.append("")
    lines.append("[products.fv_process]")
    lines.extend(_fv_lines(fit))
    lines.append("")
    lines.append("[products.bot1]")
    lines.extend(_bot1_lines(bots["bot1"]))
    lines.append("")
    lines.append("[products.bot2]")
    lines.extend(_bot2_lines(bots["bot2"]))
    lines.append("")
    lines.append("[products.bot3]")
    lines.extend(_bot3_lines(bots["bot3"]))
    lines.append("")
    lines.append("[products.taker]")
    lines.extend(_taker_lines(bots["taker"]))
    return "\n".join(lines)


# --- public API ---

def emit_round1_toml(
    *,
    osmium_fit: Path,
    osmium_bots: Path,
    pepper_fit: Path,
    pepper_bots: Path,
    out: Path,
) -> None:
    osm_fit = json.loads(osmium_fit.read_text())
    osm_bots = json.loads(osmium_bots.read_text())
    pep_fit = json.loads(pepper_fit.read_text())
    pep_bots = json.loads(pepper_bots.read_text())

    sections = [
        "[meta]",
        "round = 1",
        "ticks_per_day = 10000",
        "shared_position_limit = 80",
        "",
        _product_block("ASH_COATED_OSMIUM", 80, osm_fit, osm_bots),
        "",
        _product_block("INTARIAN_PEPPER_ROOT", 80, pep_fit, pep_bots),
        "",
    ]
    out.write_text("\n".join(sections))


# --- CLI ---

def _cli() -> None:
    p = argparse.ArgumentParser(description="emit configs/round1.toml from calibration artifacts")
    p.add_argument("--osmium-fit", type=Path, required=True)
    p.add_argument("--osmium-bots", type=Path, required=True)
    p.add_argument("--pepper-fit", type=Path, required=True)
    p.add_argument("--pepper-bots", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    emit_round1_toml(
        osmium_fit=args.osmium_fit,
        osmium_bots=args.osmium_bots,
        pepper_fit=args.pepper_fit,
        pepper_bots=args.pepper_bots,
        out=args.out,
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    _cli()
