"""CoinGecko parsing tests."""
from __future__ import annotations

from etl.sources.coingecko import parse_markets


MARKETS = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "current_price": 79255.0,
        "market_cap": 1591254168516.0,
        "market_cap_rank": 1,
        "total_volume": 56842173154.0,
        "high_24h": 81160.0,
        "low_24h": 76000.0,
    }
]


def test_parse_markets_maps_snapshot_row():
    rows = list(parse_markets(MARKETS, snapshot_date="2026-08-25"))
    assert len(rows) == 1
    row = rows[0]
    assert row["coin_id"] == "bitcoin"
    assert row["symbol"] == "btc"
    assert row["name"] == "Bitcoin"
    assert row["snapshot_date"] == "2026-08-25"
    assert row["current_price"] == 79255.0
    assert row["market_cap"] == 1591254168516.0
    assert row["market_cap_rank"] == 1


def test_parse_markets_handles_empty_list():
    assert list(parse_markets([], snapshot_date="2026-08-25")) == []
