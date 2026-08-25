"""CoinGecko market snapshot fetcher and parser."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import urlopen


def fetch_markets(coin_ids: list[str]) -> list[dict[str, Any]]:
    query = ",".join(coin_ids)
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&ids={query}&per_page=250"
    )
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_markets(
    payload: list[dict[str, Any]], snapshot_date: str
) -> Iterator[dict[str, Any]]:
    for item in payload:
        yield {
            "coin_id": item["id"],
            "symbol": item["symbol"],
            "name": item["name"],
            "snapshot_date": snapshot_date,
            "current_price": item.get("current_price"),
            "market_cap": item.get("market_cap"),
            "total_volume": item.get("total_volume"),
            "high_24h": item.get("high_24h"),
            "low_24h": item.get("low_24h"),
            "market_cap_rank": item.get("market_cap_rank"),
        }
