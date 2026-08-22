"""Domain universe data tests."""
from domain.universe_data import MARKETS, find_symbol, universe_for


def test_markets_cover_expected_ids():
    ids = {m["id"] for m in MARKETS}
    assert {"a-share", "us", "kr", "hk", "fund", "fx", "crypto"} <= ids


def test_find_symbol_and_universe_for():
    item = find_symbol("us", "AAPL")
    assert item is not None
    assert item["market"] == "us"
    assert universe_for("us")
