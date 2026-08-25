"""World Bank indicator fetcher and parser."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import urlopen


def fetch_indicator(country_code: str, indicator_code: str) -> list[dict[str, Any]]:
    url = (
        "https://api.worldbank.org/v2/country/"
        f"{country_code}/indicator/{indicator_code}?format=json&per_page=100"
    )
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_indicator(payload: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    records = payload[1] if len(payload) > 1 else []
    for item in records:
        value = item.get("value")
        if value is None:
            continue
        yield {
            "country_code": item["country"]["id"],
            "indicator_code": item["indicator"]["id"],
            "indicator_name": item["indicator"]["value"],
            "date": item["date"],
            "value": value,
        }
