"""Discovery tests (network and akshare mocked)."""
from __future__ import annotations

import pandas as pd
import pytest

from etl.sources import discovery


@pytest.fixture(autouse=True)
def clear_discovery_cache():
    discovery._discovery_cache.clear()
    yield
    discovery._discovery_cache.clear()


def test_discover_us_kr_fx_use_static_universe(monkeypatch):
    items = discovery.discover_instruments("us")
    assert any(item["symbol"] == "AAPL" for item in items)

    items_kr = discovery.discover_instruments("kr")
    assert any(item["symbol"] == "005930.KS" for item in items_kr)

    items_fx = discovery.discover_instruments("fx")
    assert any(item["symbol"] == "USDCNY=X" for item in items_fx)


def test_discover_crypto_parses_gate_tickers(monkeypatch):
    payload = [
        {"currency_pair": "BTC_USDT", "quote_volume": "1000"},
        {"currency_pair": "ETH_USDT", "quote_volume": "900"},
        {"currency_pair": "BTC_ETH", "quote_volume": "999"},
        {"currency_pair": "USDT_USDT", "quote_volume": "1"},
    ]
    monkeypatch.setattr(discovery, "get_json", lambda url, **kw: payload)
    items = discovery.discover_instruments("crypto")
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
        discovery,
        "_ak",
        lambda: type("AK", (), {"stock_zh_a_spot_em": lambda: frame}),
    )
    items = discovery.discover_instruments("a-share")
    assert {item["symbol"] for item in items} == {"600519", "000001"}
    assert all(item["market"] == "a-share" for item in items)
