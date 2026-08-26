"""Static universe configuration tests."""
from __future__ import annotations

from etl.universe import CONFIG_MARKETS, static_universe


def test_static_universe_covers_us_and_kr():
    symbols = {item["symbol"] for item in static_universe()}
    assert {"AAPL", "NVDA", "MSFT", "TSLA"} <= symbols
    assert {"005930.KS", "000660.KS"} <= symbols


def test_static_universe_has_market_and_currency():
    for item in static_universe():
        assert item["market"] in CONFIG_MARKETS
        assert item["currency"]


def test_fx_universe_has_major_pairs():
    symbols = {item["symbol"] for item in static_universe() if item["market"] == "fx"}
    assert {"USDCNY=X", "EURUSD=X"} <= symbols
