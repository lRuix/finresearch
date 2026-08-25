"""World Bank parsing tests."""
from __future__ import annotations

from etl.sources.worldbank import parse_indicator


PAYLOAD = [
    {"page": 1, "pages": 1, "per_page": 50, "total": 1},
    [
        {
            "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
            "country": {"id": "CN", "value": "China"},
            "countryiso3code": "CHN",
            "date": "2025",
            "value": 19498039388042.6,
        }
    ],
]


def test_parse_indicator_maps_rows():
    rows = list(parse_indicator(PAYLOAD))
    assert len(rows) == 1
    row = rows[0]
    assert row["country_code"] == "CN"
    assert row["indicator_code"] == "NY.GDP.MKTP.CD"
    assert row["indicator_name"] == "GDP (current US$)"
    assert row["date"] == "2025"
    assert row["value"] == 19498039388042.6


def test_parse_indicator_skips_null_values():
    payload = [
        {"page": 1, "pages": 1, "per_page": 50, "total": 1},
        [
            {
                "indicator": {"id": "X", "value": "X"},
                "country": {"id": "CN", "value": "China"},
                "countryiso3code": "CHN",
                "date": "2025",
                "value": None,
            }
        ],
    ]
    assert list(parse_indicator(payload)) == []
