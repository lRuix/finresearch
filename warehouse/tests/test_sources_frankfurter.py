"""Frankfurter kline source tests."""
from __future__ import annotations

from etl.sources import frankfurter


def test_fetch_klines_preserves_fx_fields_and_filters(monkeypatch):
    payload = {
        "rates": {
            "2026-08-22": {"CNY": "7.18"},
            "2026-08-23": {"CNY": "7.20"},
            "2026-08-24": {"CNY": "7.22"},
        }
    }
    monkeypatch.setattr(frankfurter, "get_json", lambda url, **kw: payload)

    rows = frankfurter.fetch_klines(
        "fx",
        "USDCNY=X",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23"
    assert rows[0]["base"] == "USD"
    assert rows[0]["quote"] == "CNY"
    assert rows[0]["rate"] == 7.2
    assert rows[0]["open"] == 7.18
    assert rows[0]["high"] == 7.2
    assert rows[0]["low"] == 7.18
    assert rows[0]["close"] == 7.2
    assert rows[0]["volume"] == 0.0
