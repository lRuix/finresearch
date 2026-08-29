"""Eastmoney fund kline source tests."""
from __future__ import annotations

from etl.sources import eastmoney


def test_fetch_klines_preserves_nav_fields_and_filters(monkeypatch):
    payload = {
        "Data": {
            "LSJZList": [
                {
                    "FSRQ": "2026-08-24",
                    "DWJZ": "2.900",
                    "LJJZ": "2.896",
                    "JZZZL": "-1.33",
                },
                {
                    "FSRQ": "2026-08-23",
                    "DWJZ": "2.950",
                    "LJJZ": "2.946",
                    "JZZZL": "1.02",
                },
                {
                    "FSRQ": "2026-08-22",
                    "DWJZ": "2.920",
                    "LJJZ": "2.916",
                    "JZZZL": "0.50",
                },
            ]
        }
    }
    monkeypatch.setattr(eastmoney, "get_json", lambda url, **kw: payload)

    rows = eastmoney.fetch_klines(
        "fund",
        "110022",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23"
    assert rows[0]["nav"] == 2.95
    assert rows[0]["accum_nav"] == 2.946
    assert rows[0]["daily_growth_pct"] == 1.02
    assert rows[0]["open"] == 2.95
    assert rows[0]["close"] == 2.95
