"""CatalogService tests."""
from application.services.catalog_service import CatalogService
from domain.universe_data import MARKETS


def test_markets_returns_all_markets():
    result = CatalogService().markets()
    assert result["total"] == len(MARKETS)
    assert {item["id"] for item in result["items"]} == {m["id"] for m in MARKETS}


def test_universe_filters_by_market():
    result = CatalogService().universe("us")
    assert result["total"] == len(result["items"])
    assert all(item["market"] == "us" for item in result["items"])
