"""SymbolResolver tests using fake datasource."""
from unittest.mock import patch

from application.services.symbol_resolver import SymbolResolver
from domain.models import KlineRow


def test_detect_and_normalize_market():
    resolver = SymbolResolver(datasource=None)
    assert resolver.detect_market("AAPL") == "us"
    assert resolver.detect_market("688836") == "a-share"
    assert resolver.normalize_symbol("kr", "005930") == "005930.KS"


def test_resolve_meta_probes_datasource_when_not_curated():
    class FakeDatasource:
        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            return [
                KlineRow(
                    time=f"2026-08-{i:02d}", open=1.0, high=1.0,
                    low=1.0, close=100.0 + i, volume=1000,
                )
                for i in range(1, 61)
            ]

    resolver = SymbolResolver(datasource=FakeDatasource())
    meta = resolver.resolve_meta("us", "ZZZZ")
    assert meta is not None
    assert meta["symbol"] == "ZZZZ"
    assert meta["auto"] is True
