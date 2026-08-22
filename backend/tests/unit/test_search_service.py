"""SearchService tests."""
from unittest.mock import MagicMock

from application.services.search_service import SearchService


def test_search_matches_universe_symbol_without_probe():
    datasource = MagicMock()
    result = SearchService(datasource).search("AAPL")
    assert result["items"][0]["symbol"] == "AAPL"
    assert result["items"][0]["matched"] == "universe"
    datasource.get_klines.assert_not_called()


def test_search_empty_query_returns_no_items():
    datasource = MagicMock()
    result = SearchService(datasource).search("")
    assert result == {"query": "", "items": [], "total": 0}
    datasource.get_klines.assert_not_called()


def test_search_delegates_unknown_symbol_to_resolver():
    resolver = MagicMock()
    resolver.detect_market.return_value = "us"
    resolver.normalize_symbol.return_value = "ZZZZ"
    resolver.resolve_meta.return_value = {
        "symbol": "ZZZZ",
        "name": "ZZZZ (美股)",
        "market": "us",
        "currency": "USD",
        "sector": "未分类",
        "base_risk": 0.65,
        "liquidity": 0.7,
        "auto": True,
    }
    result = SearchService(datasource=object(), symbol_resolver=resolver).search("ZZZZ")
    assert result["items"] == [
        {
            "symbol": "ZZZZ",
            "name": "ZZZZ (美股)",
            "market": "us",
            "currency": "USD",
            "sector": "未分类",
            "base_risk": 0.65,
            "liquidity": 0.7,
            "auto": True,
            "matched": "auto",
        }
    ]
