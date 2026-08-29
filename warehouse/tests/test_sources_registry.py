from etl.sources import registry


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
