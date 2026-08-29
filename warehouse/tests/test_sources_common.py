from datetime import date
from etl.sources import common


def test_parse_ts_handles_z_and_naive():
    assert common.parse_ts("2026-08-29T08:00:00Z").tzinfo is not None
    assert common.parse_ts("2026-08-29").date() == date(2026, 8, 29)


def test_aggregate_weekly_groups_iso_week():
    rows = [
        {"time": "2026-08-24T08:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": "2026-08-25T08:00:00+00:00", "open": 1.5, "high": 3, "low": 1, "close": 2.5, "volume": 20},
    ]
    result = common.aggregate_weekly(rows)
    assert len(result) == 1
    assert result[0]["open"] == 1
    assert result[0]["close"] == 2.5
    assert result[0]["volume"] == 30


def test_parse_fx_symbol_supports_yahoo_and_slash_forms():
    assert common.parse_fx_symbol("USDCNY=X") == ("USD", "CNY")
    assert common.parse_fx_symbol("EUR/USD") == ("EUR", "USD")
