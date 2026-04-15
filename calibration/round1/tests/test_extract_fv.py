import json
from pathlib import Path

import pytest

from calibration.round1.scripts.extract_fv_and_book import (
    extract_product_fv_series,
    extract_book_series,
    FvPoint,
)


def _mini_activities_log() -> str:
    return (
        "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;"
        "bid_price_3;bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;"
        "ask_price_3;ask_volume_3;mid_price;profit_and_loss\n"
        "0;0;ASH_COATED_OSMIUM;9992;23;;;;;10011;13;;;;;10001.5;0.0\n"
        "0;0;INTARIAN_PEPPER_ROOT;11991;20;;;;;12006;11;12009;20;;;11998.5;0.0\n"
        "0;100;ASH_COATED_OSMIUM;9995;10;9992;23;;;10011;13;;;;;10003.0;-3.0\n"
        "0;100;INTARIAN_PEPPER_ROOT;11994;12;11991;20;;;12010;20;;;;;12002.0;-5.90\n"
    )


def _mini_submission(tmp_path: Path) -> Path:
    log = {
        "round": "Round 1",
        "status": "Completed",
        "profit": 85.6,
        "activitiesLog": _mini_activities_log(),
        "graphLog": "timestamp;value\n0;0.0\n100;-8.9\n",
        "positions": [
            {"symbol": "ASH_COATED_OSMIUM", "quantity": 1},
            {"symbol": "INTARIAN_PEPPER_ROOT", "quantity": 1},
            {"symbol": "XIRECS", "quantity": -22017},
        ],
    }
    p = tmp_path / "mini.json"
    p.write_text(json.dumps(log))
    return p


def test_extract_product_fv_series_recovers_server_fv(tmp_path):
    sub = _mini_submission(tmp_path)
    osmium = extract_product_fv_series(sub, "ASH_COATED_OSMIUM")
    assert len(osmium) == 2
    assert osmium[0] == FvPoint(timestamp=0, fv=10011.0, pnl=0.0, buy_price=10011.0)
    # at t=100, pnl = -3.0 => fv = -3 + 10011 = 10008
    assert osmium[1].fv == pytest.approx(10008.0)

    pepper = extract_product_fv_series(sub, "INTARIAN_PEPPER_ROOT")
    assert pepper[0].fv == pytest.approx(12006.0)
    # at t=100, pnl = -5.90 => fv = 12000.10
    assert pepper[1].fv == pytest.approx(12000.10)


def test_extract_product_fv_series_errors_on_missing_product(tmp_path):
    sub = _mini_submission(tmp_path)
    with pytest.raises(ValueError, match="no rows"):
        extract_product_fv_series(sub, "UNSEEN_PRODUCT")


def test_extract_book_series_has_three_levels_and_drops_empties(tmp_path):
    sub = _mini_submission(tmp_path)
    book = extract_book_series(sub, "INTARIAN_PEPPER_ROOT")
    assert len(book) == 2
    first = book[0]
    assert first["timestamp"] == 0
    # t=0: bid level 1 = (11991, 20); ask 1 = (12006, 11), ask 2 = (12009, 20)
    assert first["bids"] == [(11991, 20)]
    assert first["asks"] == [(12006, 11), (12009, 20)]
    second = book[1]
    assert second["bids"] == [(11994, 12), (11991, 20)]
    assert second["asks"] == [(12010, 20)]
