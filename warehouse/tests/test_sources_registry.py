import pytest

from etl.sources import common, registry


@pytest.fixture(autouse=True)
def _clear_cache():
    common._cache.clear()
    common._dead_providers.clear()
    yield
    common._cache.clear()
    common._dead_providers.clear()


def test_fetch_klines_uses_first_successful_source(monkeypatch):
    calls = []

    def ok(market, symbol, period="d", start=None, end=None, limit=1000):
        calls.append("ok")
        return [{"time": "2026-08-29", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    def empty(market, symbol, period="d", start=None, end=None, limit=1000):
        calls.append("empty")
        return []

    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("empty", empty), ("ok", ok)])
    rows = registry.fetch_klines("a-share", "600519", "d")
    assert len(rows) == 1
    assert calls == ["empty", "ok"]


def test_disabled_source_is_skipped(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_SOURCE_DISABLED", "empty")
    monkeypatch.setitem(
        registry.SOURCE_CHAINS,
        "a-share",
        [("empty", lambda *a, **k: []), ("ok", lambda *a, **k: [{"time": "2026-08-29"}])],
    )
    names = [name for name, _ in registry.enabled_sources("a-share", "600519")]
    assert names == ["ok"]


def test_all_sources_fail_returns_empty(monkeypatch):
    monkeypatch.setitem(
        registry.SOURCE_CHAINS,
        "a-share",
        [("one", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))],
    )
    assert registry.fetch_klines("a-share", "600519", "d") == []


def test_fetch_klines_with_source_returns_actual_source_name(monkeypatch):
    def ok(market, symbol, period="d", start=None, end=None, limit=1000):
        return [{"time": "2026-08-29", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("tencent", ok)])
    rows, source = registry.fetch_klines_with_source("a-share", "600519", "d")
    assert len(rows) == 1
    assert source == "tencent"

    cached_rows, cached_source = registry.fetch_klines_with_source("a-share", "600519", "d")
    assert cached_rows == rows
    assert cached_source == "tencent"


def test_fetch_klines_with_source_failure_returns_empty_and_none(monkeypatch):
    def boom(market, symbol, period="d", start=None, end=None, limit=1000):
        raise RuntimeError("boom")

    monkeypatch.setitem(registry.SOURCE_CHAINS, "crypto", [("gate", boom)])
    assert registry.fetch_klines_with_source("crypto", "BTCUSDT", "d") == ([], None)


def test_cache_key_includes_start_and_end(monkeypatch):
    earlier = {"time": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    latest = {"time": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    calls = []

    def filtered(market, symbol, period="d", start=None, end=None, limit=1000):
        calls.append((start, end))
        if start == "2026-01-01":
            return [latest]
        return [earlier, latest]

    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("tencent", filtered)])
    registry.fetch_klines("a-share", "600519", "d", start="2026-01-01", end="2026-12-31")
    earlier_rows = registry.fetch_klines(
        "a-share", "600519", "d", start="2024-01-01", end="2026-12-31"
    )

    assert [row["time"] for row in earlier_rows] == ["2024-01-02", "2026-01-02"]
    assert len(calls) == 2


def test_cache_hit_does_not_filter_stored_rows_again(monkeypatch):
    earlier = {"time": "2024-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    latest = {"time": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
    calls = []

    def unfiltered(market, symbol, period="d", start=None, end=None, limit=1000):
        calls.append("call")
        return [earlier, latest]

    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("tencent", unfiltered)])
    registry.fetch_klines("a-share", "600519", "d", start="2026-01-01", end="2026-12-31")
    cached_rows = registry.fetch_klines(
        "a-share", "600519", "d", start="2026-01-01", end="2026-12-31"
    )

    assert len(cached_rows) == 2
    assert calls == ["call"]
