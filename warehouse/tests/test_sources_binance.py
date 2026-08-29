"""Binance kline source tests."""
from __future__ import annotations

from etl.sources import binance


def test_fetch_klines_preserves_binance_fields_and_filters(monkeypatch):
    payload = [
        [
            1787356800000, "78338.03", "78828.15", "76500.00", "77074.93",
            "18524.50", 1787443199999, "1433768388.59", 3950045,
            "9413.19", "728650560.29", "0",
        ],
        [
            1787443200000, "78500.00", "78900.00", "77000.00", "77500.00",
            "19000.00", 1787529599999, "1460000000.00", 4000000,
            "9500.00", "735000000.00", "0",
        ],
        [
            1787529600000, "77600.00", "78000.00", "76000.00", "77000.00",
            "19500.00", 1787615999999, "1490000000.00", 4050000,
            "9600.00", "740000000.00", "0",
        ],
    ]
    monkeypatch.setattr(binance, "get_json", lambda url, **kw: payload)

    rows = binance.fetch_klines(
        "crypto",
        "BTCUSDT",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23T00:00:00+00:00"
    assert rows[0]["quote_volume"] == 1460000000.0
    assert rows[0]["trades_count"] == 4000000
