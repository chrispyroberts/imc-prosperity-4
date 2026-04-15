"""Recover per-tick server fair value per product from a hold-1 submission log.

Philosophy: server FV is NOT the order-book mid. It is a 1/2048-quantized
value driving PnL. For a trader that bought 1 unit of each product at t=0
and holds forever:
    server_FV(product, t) = pnl(product, t) + buy_price(product)

The hold-1 submission activity log is JSON with an `activitiesLog` field
containing a CSV string (day;timestamp;product;bid_price_1;...;profit_and_loss).
The order book is inline in that CSV, three levels per side.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FvPoint:
    timestamp: int
    fv: float
    pnl: float
    buy_price: float


def _parse_activities_rows(log_path: Path) -> list[dict]:
    raw = json.loads(Path(log_path).read_text())
    csv_text = raw.get("activitiesLog", "")
    if not csv_text:
        raise ValueError(f"no activitiesLog in {log_path}")
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=";")
    return list(reader)


def _parse_float(cell: str | None) -> float | None:
    if cell is None or cell == "":
        return None
    return float(cell)


def _parse_int(cell: str | None) -> int | None:
    if cell is None or cell == "":
        return None
    return int(cell)


def _buy_price_from_first_tick(rows: list[dict], product: str) -> float:
    """The hold-1 trader buys at the best ask at t=0. We reconstruct that."""
    for row in rows:
        if row["product"] != product:
            continue
        if int(row["timestamp"]) != 0:
            continue
        ask1 = _parse_float(row.get("ask_price_1"))
        if ask1 is None:
            raise ValueError(f"no ask level at t=0 for {product}")
        return ask1
    raise ValueError(f"no rows for product {product} in activitiesLog")


def extract_product_fv_series(log_path: Path, product: str) -> list[FvPoint]:
    rows = _parse_activities_rows(log_path)
    buy_price = _buy_price_from_first_tick(rows, product)
    points: list[FvPoint] = []
    for row in rows:
        if row["product"] != product:
            continue
        pnl = _parse_float(row.get("profit_and_loss"))
        if pnl is None:
            continue
        ts = int(row["timestamp"])
        points.append(FvPoint(timestamp=ts, fv=pnl + buy_price, pnl=pnl, buy_price=buy_price))
    if not points:
        raise ValueError(f"no rows for product {product} in activitiesLog")
    points.sort(key=lambda p: p.timestamp)
    return points


def extract_book_series(log_path: Path, product: str) -> list[dict]:
    """Returns [{timestamp, bids:[(price,qty),...], asks:[(price,qty),...]}, ...].
    Each side sorted by price (bids descending, asks ascending).
    """
    rows = _parse_activities_rows(log_path)
    series: list[dict] = []
    for row in rows:
        if row["product"] != product:
            continue
        ts = int(row["timestamp"])
        bids = []
        for i in (1, 2, 3):
            p = _parse_int(row.get(f"bid_price_{i}"))
            q = _parse_int(row.get(f"bid_volume_{i}"))
            if p is not None and q is not None:
                bids.append((p, q))
        asks = []
        for i in (1, 2, 3):
            p = _parse_int(row.get(f"ask_price_{i}"))
            q = _parse_int(row.get(f"ask_volume_{i}"))
            if p is not None and q is not None:
                asks.append((p, q))
        bids.sort(key=lambda x: -x[0])
        asks.sort(key=lambda x: x[0])
        series.append({"timestamp": ts, "bids": bids, "asks": asks})
    series.sort(key=lambda s: s["timestamp"])
    return series


def main(log_path: Path, out_dir: Path, products: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for product in products:
        fv = extract_product_fv_series(log_path, product)
        book = extract_book_series(log_path, product)
        # mid-price sanity: how many ticks differ from server FV by > 1.5?
        outliers = 0
        total = 0
        for tick in fv:
            snap = next((b for b in book if b["timestamp"] == tick.timestamp), None)
            if snap and snap["bids"] and snap["asks"]:
                mid = (snap["bids"][0][0] + snap["asks"][0][0]) / 2.0
                total += 1
                if abs(tick.fv - mid) > 1.5:
                    outliers += 1
        if total > 0 and outliers / total > 0.01:
            print(f"WARN {product}: {outliers}/{total} ticks have |fv-mid| > 1.5 "
                  f"({100*outliers/total:.1f}%) -- asymmetric-book investigation warranted")

        slug = product.lower()
        merged = {
            "product": product,
            "buy_price": fv[0].buy_price if fv else None,
            "ticks": [{"timestamp": p.timestamp, "fv": p.fv, "pnl": p.pnl} for p in fv],
            "book": book,
        }
        out = out_dir / f"fv_and_book_{slug}.json"
        out.write_text(json.dumps(merged, indent=2))
        print(f"wrote {out} ({len(fv)} ticks, {len(book)} book snapshots)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--products", nargs="+",
                        default=["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"])
    args = parser.parse_args()
    main(args.log_path, args.out, args.products)
