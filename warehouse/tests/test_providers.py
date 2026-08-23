"""Provider parsing tests."""
from etl.providers import parse_binance_klines, parse_gate_klines, parse_eastmoney_fund


def test_parse_binance_klines():
    raw = [[
        1787356800000, "78338.03", "78828.15", "76500.00",
        "77074.93", "18524.50", 1787443199999, "1433768388.59",
        3950045, "9413.19", "728650560.29", "0",
    ]]
    rows = parse_binance_klines(raw)
    assert rows[0]["quote_volume"] == 1433768388.59
    assert rows[0]["trades_count"] == 3950045


def test_parse_gate_klines():
    raw = [["1787356800", "808872838.726", "77078", "78835.1", "76500", "78336", "10439.731", "true"]]
    rows = parse_gate_klines(raw)
    assert rows[0]["quote_volume"] == 808872838.726
    assert rows[0]["volume"] == 10439.731


def test_parse_eastmoney_fund():
    item = {
        "FSRQ": "2026-08-21", "DWJZ": "2.8960", "LJJZ": "2.8960",
        "JZZZL": "-1.33", "SGZT": "开放申购", "SHZT": "开放赎回",
    }
    row = parse_eastmoney_fund(item)
    assert row["nav"] == 2.8960
    assert row["daily_growth_pct"] == -1.33
