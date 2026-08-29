"""Naver kline source tests."""
from __future__ import annotations

from etl.sources import naver


def test_fetch_klines_parses_items_and_filters(monkeypatch):
    text = """
    <chart>
      <item data="20260822|100|101|99|100.5|12345"/>
      <item data="20260823|100.5|102|100|101|13000"/>
      <item data="20260824|101|103|100.5|102|14000"/>
    </chart>
    """
    monkeypatch.setattr(naver, "get_text", lambda url, **kw: text)

    rows = naver.fetch_klines(
        "kr",
        "005930.KS",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23"
    assert rows[0]["open"] == 100.5
    assert rows[0]["high"] == 102
    assert rows[0]["low"] == 100
    assert rows[0]["close"] == 101
    assert rows[0]["volume"] == 13000
