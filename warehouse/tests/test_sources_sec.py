"""SEC EDGAR parsing tests."""
from __future__ import annotations

from etl.sources.sec_edgar import parse_facts, parse_submissions


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
