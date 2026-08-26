"""Market discovery and kline fetching tests (network mocked)."""
from __future__ import annotations

import pandas as pd

from etl.sources import market


def test_discover_us_and_kr_use_static_universe(monkeypatch):
    items = market.discover_instruments("us")
    assert any(item["symbol"] == "AAPL" for item in items)
    items_kr = market.discover_instruments("kr")
    assert any(item["symbol"] == "005930.KS" for item in items_kr)


def test_discover_crypto_parses_gate_tickers(monkeypatch):
    payload = [
        {"currency_pair": "BTC_USDT", "quote_volume": "1000"},
        {"currency_pair": "ETH_USDT", "quote_volume": "900"},
        {"currency_pair": "BTC_ETH", "quote_volume": "999"},
        {"currency_pair": "USDT_USDT", "quote_volume": "1"},
    ]
    monkeypatch.setattr(market, "_get_json", lambda url, **kw: payload)
    items = market.discover_instruments("crypto")
    symbols = {item["symbol"] for item in items}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


def test_discover_a_share_uses_akshare_spot(monkeypatch):
    frame = pd.DataFrame(
        {
            "代码": ["600519", "000001"],
            "名称": ["贵州茅台", "平安银行"],
            "成交额": [1e9, 2e9],
        }
    )

    monkeypatch.setattr(
        market,
        "_ak",
        lambda: type("AK", (), {"stock_zh_a_spot_em": lambda: frame}),
    )
    items = market.discover_instruments("a-share")
    assert {item["symbol"] for item in items} == {"600519", "000001"}
    assert all(item["market"] == "a-share" for item in items)
