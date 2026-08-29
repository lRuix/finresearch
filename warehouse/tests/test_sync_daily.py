from etl import sync_daily
from etl.sources import registry


def test_main_uses_dynamic_discover_fallback_and_restores_registry(monkeypatch):
    calls = []

    def discover(market):
        calls.append(market)
        if market == "us":
            return [{
                "symbol": "DYNAMIC-US",
                "name": "Dynamic US",
                "market": "us",
                "currency": "USD",
            }]
        raise RuntimeError("dynamic unavailable")

    def sync_main():
        dynamic_rows = registry.discover_instruments("us")
        assert dynamic_rows[0]["symbol"] == "DYNAMIC-US"
        fallback_rows = registry.discover_instruments("a-share")
        assert fallback_rows[0]["symbol"] == "600519"

    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr("etl.sync_incremental.main", sync_main)
    assert sync_daily.main() == 0
    assert calls == ["us", "a-share"]
    assert registry.discover_instruments is discover
