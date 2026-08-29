"""Tencent kline source tests."""
from __future__ import annotations

from etl.sources import tencent


def test_fetch_klines_parses_rows_and_filters(monkeypatch):
    payload = {
        "data": {
            "sh600519": {
                "day": [
                    ["2026-08-01", "10", "10.5", "11", "9", "100"],
                    ["2026-08-02", "10.5", "11", "12", "10", "120"],
                    ["2026-08-03", "11", "11.5", "12", "10.5", "130"],
                ]
            }
        }
    }
    monkeypatch.setattr(tencent, "get_json", lambda url, **kw: payload)

    rows = tencent.fetch_klines(
        "a-share",
        "600519",
        "d",
        start="2026-08-02",
        end="2026-08-02",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-02"
    assert rows[0]["open"] == 10.5
    assert rows[0]["close"] == 11
    assert rows[0]["volume"] == 120
