"""SymbolResolver tests using fake datasource."""
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


def test_normalize_crypto_no_duplicate_suffix():
    resolver = SymbolResolver(datasource=None)
    assert resolver.normalize_symbol("crypto", "BTCUSDT") == "BTCUSDT"
    assert resolver.normalize_symbol("crypto", "BTC") == "BTCUSDT"


def test_normalize_kr_keeps_kq_and_ashare_strips_suffix():
    resolver = SymbolResolver(datasource=None)
    assert resolver.normalize_symbol("kr", "005930.KQ") == "005930.KQ"
    assert resolver.normalize_symbol("kr", "005930.KS") == "005930.KS"
    assert resolver.normalize_symbol("a-share", "600519.SH") == "600519"


def test_detect_market_suffix_consistent_with_bare_code():
    resolver = SymbolResolver(datasource=None)
    assert resolver.detect_market("510300.SH") == "fund"
    assert resolver.detect_market("600519.SH") == "a-share"
    assert resolver.detect_market("000001.SZ") == "a-share"
    assert resolver.detect_market("510300") == "fund"
    assert resolver.detect_market("600519") == "a-share"
    assert resolver.detect_market("000001") == "a-share"
    assert resolver.normalize_symbol("fund", "510300.SH") == "510300"
    assert resolver.detect_market("AEROSOL") == "us"
    assert resolver.detect_market("METH") == "us"
    assert resolver.detect_market("中国") is None


def test_resolve_meta_uses_curated_without_probe():
    calls = {"count": 0}

    class FakeDatasource:
        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            calls["count"] += 1
            return []

    resolver = SymbolResolver(datasource=FakeDatasource())
    meta = resolver.resolve_meta("us", "AAPL")
    assert meta is not None
    assert meta["auto"] is False
    assert calls["count"] == 0


def test_detect_normalize_resolve_chain_hits_curated():
    calls = {"count": 0}

    class FakeDatasource:
        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            calls["count"] += 1
            return []

    resolver = SymbolResolver(datasource=FakeDatasource())
    market = resolver.detect_market("510300.SH")
    symbol = resolver.normalize_symbol(market, "510300.SH")
    assert (market, symbol) == ("fund", "510300")
    meta = resolver.resolve_meta(market, symbol)
    assert meta is not None
    assert meta["symbol"] == "510300"
    assert meta["auto"] is False
    assert calls["count"] == 0


def test_resolve_meta_none_when_no_rows():
    class FakeDatasource:
        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            return []

    resolver = SymbolResolver(datasource=FakeDatasource())
    assert resolver.resolve_meta("us", "ZZZZ") is None


def test_derive_risk_uses_volatility_and_market_target():
    stable = [100.0 + i * 0.05 for i in range(60)]
    assert SymbolResolver._derive_risk(stable, "us") < 0.6


def test_derive_liquidity_uses_market_thresholds():
    crypto_rows = [KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0, 5_000_000) for i in range(20)]
    assert SymbolResolver._derive_liquidity(crypto_rows, "crypto") == 0.85
    assert SymbolResolver._derive_liquidity(crypto_rows, "fx") == 0.7
