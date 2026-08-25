"""SEC EDGAR fetchers and parsers."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import Request, urlopen


USER_AGENT = "finresearch-warehouse/1.0 (warehouse.etl@finresearch.local)"


def _get_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_submissions(cik: str) -> dict[str, Any]:
    return _get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")


def fetch_company_facts(cik: str) -> dict[str, Any]:
    return _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")


def parse_submissions(payload: dict[str, Any]) -> dict[str, Any]:
    tickers = payload.get("tickers") or []
    exchanges = payload.get("exchanges") or []
    return {
        "cik": payload["cik"],
        "ticker": tickers[0] if tickers else None,
        "company_name": payload["name"],
        "exchange": exchanges[0] if exchanges else None,
        "sic": payload.get("sic"),
    }


def parse_facts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    cik = payload["cik"]
    for taxonomy, concepts in (payload.get("facts") or {}).items():
        for concept, data in concepts.items():
            units = data.get("units") or {}
            for unit, entries in units.items():
                for entry in entries:
                    yield {
                        "cik": cik,
                        "concept": f"{taxonomy}/{concept}",
                        "unit": unit,
                        "period_end": entry["end"],
                        "value": entry.get("val"),
                    }
