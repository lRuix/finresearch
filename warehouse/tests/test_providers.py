"""Provider parsing tests."""
from etl.providers import (
    _to_float,
    _to_int,
    _to_iso_timestamp,
    parse_binance_klines,
    parse_eastmoney_fund,
    parse_gate_klines,
)


def test_parse_binance_klines_empty():
    assert parse_binance_klines([]) == []


def test_parse_gate_klines_empty():
    assert parse_gate_klines([]) == []


def test_parse_binance_klines():
    raw = [[
        1787356800000, "78338.03", "78828.15", "76500.00",
        "77074.93", "18524.50", 1787443199999, "1433768388.59",
        3950045, "9413.19", "728650560.29", "0",
    ]]
    rows = parse_binance_klines(raw)
    assert rows[0]["time"] == "2026-08-22T00:00:00+00:00"
    assert rows[0]["open"] == 78338.03
    assert rows[0]["high"] == 78828.15
    assert rows[0]["low"] == 76500.00
    assert rows[0]["close"] == 77074.93
    assert rows[0]["volume"] == 18524.50
    assert rows[0]["quote_volume"] == 1433768388.59
    assert rows[0]["trades_count"] == 3950045
    assert rows[0]["raw"] == raw[0]


def test_parse_binance_klines_none_row():
    rows = parse_binance_klines([[None]])
    assert len(rows) == 1
    row = rows[0]
    assert row["time"] is None
    assert row["open"] is None
    assert row["high"] is None
    assert row["low"] is None
    assert row["close"] is None
    assert row["volume"] is None
    assert row["quote_volume"] is None
    assert row["trades_count"] is None
    assert row["raw"] == [None]


def test_invalid_string_conversions():
    assert _to_float("abc") is None
    assert _to_int("abc") is None
    assert _to_float("") is None
    assert _to_int("") is None


def test_to_iso_timestamp_millisecond_boundary():
    assert _to_iso_timestamp(999_999_999_999) == "2001-09-09T01:46:39.999000+00:00"


def test_blank_markers_and_non_finite_floats():
    assert _to_float("null") is None
    assert _to_float("NaN") is None
    assert _to_float("inf") is None
    assert _to_float("-inf") is None
    assert _to_float("-") is None
    assert _to_int(float("inf")) is None
    assert _to_int(float("-inf")) is None
    assert _to_iso_timestamp(float("inf")) is None
    assert _to_iso_timestamp(float("-inf")) is None


def test_parse_gate_klines():
    raw = [["1787356800", "808872838.726", "77078", "78835.1", "76500", "78336", "10439.731", "true"]]
    rows = parse_gate_klines(raw)
    assert rows[0]["time"] == "2026-08-22T00:00:00+00:00"
    assert rows[0]["open"] == 78336
    assert rows[0]["high"] == 78835.1
    assert rows[0]["low"] == 76500
    assert rows[0]["close"] == 77078
    assert rows[0]["quote_volume"] == 808872838.726
    assert rows[0]["volume"] == 10439.731
    assert rows[0]["raw"] == raw[0]


def test_parse_eastmoney_fund():
    item = {
        "FSRQ": "2026-08-21", "DWJZ": "2.8960", "LJJZ": "2.8960",
        "JZZZL": "-1.33", "SGZT": "开放申购", "SHZT": "开放赎回",
    }
    row = parse_eastmoney_fund(item)
    assert row["ts"] == "2026-08-21"
    assert row["nav"] == 2.8960
    assert row["accum_nav"] == 2.8960
    assert row["daily_growth_pct"] == -1.33
    assert row["purchase_status"] == "开放申购"
    assert row["redeem_status"] == "开放赎回"
    assert row["raw"] == item


def test_parse_eastmoney_fund_missing_blank_values():
    row = parse_eastmoney_fund({"FSRQ": "2026-08-21", "DWJZ": "", "JZZZL": ""})
    assert row["ts"] == "2026-08-21"
    assert row["nav"] is None
    assert row["daily_growth_pct"] is None


def test_parse_invalid_timestamps():
    rows = parse_binance_klines([
        [-1, "1", "2", "3", "4", "5", "6", "7", 1],
        ["abc", "1", "2", "3", "4", "5", "6", "7", 1],
    ])
    assert rows[0]["time"] is None
    assert rows[1]["time"] is None
