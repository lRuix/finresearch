"""SEC EDGAR parsing tests."""
from __future__ import annotations

import gzip
import json

from etl.sources.sec_edgar import fetch_submissions, parse_facts, parse_submissions


SUBMISSIONS = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "sic": "3571",
}

FACTS = {
    "cik": "0000320193",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"end": "2025-09-27", "val": 391035000000.0},
                        {"end": "2024-09-28", "val": 383285000000.0},
                    ]
                }
            }
        }
    },
}


def test_parse_submissions_maps_company_row():
    row = parse_submissions(SUBMISSIONS)
    assert row["cik"] == "0000320193"
    assert row["ticker"] == "AAPL"
    assert row["company_name"] == "Apple Inc."
    assert row["exchange"] == "Nasdaq"
    assert row["sic"] == "3571"


def test_parse_facts_expands_concepts_without_duplicates():
    rows = list(parse_facts(FACTS))
    assert len(rows) == 2
    first = rows[0]
    assert first["cik"] == "0000320193"
    assert first["concept"] == "us-gaap/Revenues"
    assert first["unit"] == "USD"
    assert first["period_end"] == "2025-09-27"
    assert first["value"] == 391035000000.0


def test_fetch_submissions_decodes_gzip(monkeypatch):
    payload = json.dumps({"cik": "0000320193", "name": "Apple Inc."}).encode("utf-8")
    compressed = gzip.compress(payload)

    class FakeResponse:
        headers = {"Content-Encoding": "gzip"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return compressed

    monkeypatch.setattr(
        "etl.sources.sec_edgar.urlopen",
        lambda request, timeout=30: FakeResponse(),
    )
    result = fetch_submissions("0000320193")
    assert result["name"] == "Apple Inc."
