"""akshare China A-share parsing tests."""
from __future__ import annotations

from etl.sources.akshare_cn import parse_financials, parse_lhb


FINANCIALS = [
    {"报告期": "2025-12-31", "净利润": 862.3, "营业总收入": 1708.0, "净利润同比增长率": 15.2},
    {"报告期": "2025-09-30", "净利润": 600.1, "营业总收入": 1250.0, "净利润同比增长率": 12.8},
]

LHB = [
    {"上榜日": "2026-08-21", "代码": "600519", "名称": "贵州茅台", "解读": "日涨幅偏离值达7%", "收盘价": 1450.0, "涨跌幅": 8.5},
]


def test_parse_financials_expands_wide_rows():
    rows = list(parse_financials(FINANCIALS, symbol="600519"))
    assert len(rows) == 6
    assert {
        "symbol": "600519",
        "report_date": "2025-12-31",
        "indicator_name": "净利润",
        "indicator_value": 862.3,
    } in rows


def test_parse_lhb_maps_rows():
    rows = list(parse_lhb(LHB))
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_date"] == "2026-08-21"
    assert row["code"] == "600519"
    assert row["name"] == "贵州茅台"
    assert row["reason"] == "日涨幅偏离值达7%"
    assert row["close_price"] == 1450.0
    assert row["change_pct"] == 8.5
