"""跨市场代码识别与天级缓存测试。"""
from core.search import (
    daily_cache_get, daily_cache_set, detect_market, normalize_symbol,
)


def test_detect_a_share():
    assert detect_market("688836") == "a-share"
    assert detect_market("600519") == "a-share"
    assert detect_market("000001") == "a-share"


def test_detect_fund():
    assert detect_market("510300") == "fund"


def test_detect_us():
    assert detect_market("AAPL") == "us"
    assert detect_market("TSLA") == "us"


def test_detect_hk_kr():
    assert detect_market("0700.HK") == "hk"
    assert detect_market("005930.KS") == "kr"


def test_detect_fx_crypto():
    assert detect_market("USDCNY=X") == "fx"
    assert detect_market("BTCUSDT") == "crypto"


def test_normalize_hk():
    assert normalize_symbol("hk", "0700") == "0700.HK"


def test_daily_cache_roundtrip():
    daily_cache_set("key1", {"v": 1})
    assert daily_cache_get("key1") == {"v": 1}
    assert daily_cache_get("missing") is None
