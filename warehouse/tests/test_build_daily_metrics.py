"""Daily A-share derived metrics tests."""
from __future__ import annotations

import pytest

from etl.build_daily_metrics import compute_rows, shares_as_of


TABLE = {
    "600519": (
        ["2025-09-01", "2026-05-28"],
        [(1252270215.0, 1252270215.0), (1250081601.0, 1250081601.0)],
    )
}

KLINES = [
    {"symbol": "600519", "trade_date": "2026-09-21", "close": 1252.57, "volume": 25017.0}
]


def test_shares_as_of_picks_latest_change_not_after_trade_date():
    assert shares_as_of(TABLE, "600519", "2026-06-30") == (1250081601.0, 1250081601.0)
    assert shares_as_of(TABLE, "600519", "2026-01-15") == (1252270215.0, 1252270215.0)


def test_shares_as_of_returns_none_before_first_change():
    assert shares_as_of(TABLE, "600519", "2025-01-01") is None


def test_shares_as_of_returns_none_for_unknown_symbol():
    assert shares_as_of(TABLE, "000001", "2026-09-21") is None


def test_compute_rows_turnover_matches_sina_reference():
    """600519 于 2026-09-21：新浪 turnover 实测 0.0020012（小数）= 0.20012%。"""
    rows = list(compute_rows(KLINES, TABLE))
    assert len(rows) == 1
    assert rows[0]["turnover_rate"] == pytest.approx(0.20012, rel=1e-3)
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)


def test_compute_rows_skips_symbol_without_shares():
    klines = [{"symbol": "000001", "trade_date": "2026-09-21", "close": 10.0, "volume": 100.0}]
    assert list(compute_rows(klines, TABLE)) == []


def test_compute_rows_leaves_turnover_null_when_float_shares_missing():
    table = {"600519": (["2026-05-28"], [(1250081601.0, None)])}
    rows = list(compute_rows(KLINES, table))
    assert rows[0]["turnover_rate"] is None
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)
