"""yfinance kline source tests."""
from __future__ import annotations

import pandas as pd

from etl.sources import yfinance


def test_fetch_klines_preserves_yfinance_fields_and_filters(monkeypatch):
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1000, 1100, 1200],
            "Adj Close": [99.5, 100.5, 101.5],
            "Dividends": [0.0, 0.5, 0.0],
            "Stock Splits": [0.0, 0.0, 2.0],
        },
        index=pd.to_datetime(["2026-08-22", "2026-08-23", "2026-08-24"], utc=True),
    )

    class FakeTicker:
        def history(self, **kwargs):
            return frame

    class FakeYFinance:
        def Ticker(self, ticker):
            return FakeTicker()

    monkeypatch.setattr(yfinance, "_yf", lambda: FakeYFinance())

    rows = yfinance.fetch_klines(
        "us",
        "AAPL",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23T00:00:00"
    assert rows[0]["open"] == 101.0
    assert rows[0]["close"] == 101.5
    assert rows[0]["adj_close"] == 100.5
    assert rows[0]["dividends"] == 0.5
    assert rows[0]["stock_splits"] == 0.0
