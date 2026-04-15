"""Tag each book level as bot1/bot2/bot3 based on |offset from FV|."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


# outer: bot1 (wall), inner: bot2 (mid), inside: bot3 (tight)
# OSMIUM: three clear clusters at ~8, ~10-11, and ~1-3 from FV
# PEPPER: clusters at ~6-7 and ~9-10 from FV
THRESHOLDS = {
    "ASH_COATED_OSMIUM": {"outer": 9.0, "inner": 5.0},
    "INTARIAN_PEPPER_ROOT": {"outer": 8.5, "inner": 5.0},
}


@dataclass(frozen=True)
class TaggedLevel:
    timestamp: int
    side: str
    price: int
    quantity: int
    offset: float  # price - fv (signed)
    bot: str


def classify(fv_and_book_path: Path, product: str) -> list[TaggedLevel]:
    raw = json.loads(fv_and_book_path.read_text())
    fv_by_ts = {tick["timestamp"]: tick["fv"] for tick in raw["ticks"]}
    th = THRESHOLDS[product]
    tagged: list[TaggedLevel] = []
    for snap in raw["book"]:
        fv = fv_by_ts.get(snap["timestamp"])
        if fv is None:
            continue
        for side, entries in (("bid", snap["bids"]), ("ask", snap["asks"])):
            for price, qty in entries:
                offset = price - fv
                mag = abs(offset)
                if mag >= th["outer"]:
                    bot = "bot1"
                elif mag >= th["inner"]:
                    bot = "bot2"
                else:
                    bot = "bot3"
                tagged.append(TaggedLevel(
                    timestamp=snap["timestamp"], side=side,
                    price=price, quantity=qty, offset=offset, bot=bot,
                ))
    return tagged
