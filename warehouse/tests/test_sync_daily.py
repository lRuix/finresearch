from etl import sync_daily
from etl.sources import registry


def test_main_uses_static_discover_and_returns_zero(monkeypatch):
    calls = []

    def discover(market):
        calls.append(market)
        return []

    def sync_main():
        assert registry.discover_instruments("us")[0]["symbol"] == "AAPL"
        registry.discover_instruments("fallback-only")

    monkeypatch.setattr(registry, "discover_instruments", discover)
    monkeypatch.setattr("etl.sync_incremental.main", sync_main)
    assert sync_daily.main() == 0
    assert calls
