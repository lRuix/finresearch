"""Sina balance sheet source tests."""
from __future__ import annotations

import math

import pytest

from etl.sources.sina_cn import parse_balance_sheet, sina_symbol


BALANCE_SHEET = [
    {
        "报告日": "20260630",
        "资产总计": 309050784569.31,
        "负债合计": 46954432394.95,
        "所有者权益": math.nan,
        "归属于母公司股东权益合计": 251253594419.5,
        "所有者权益(或股东权益)合计": 262096352174.36,
    },
    {
        "报告日": "20260331",
        "资产总计": 319918844905.58,
        "所有者权益": math.nan,
        "归属于母公司股东权益合计": 270894035676.27,
        "所有者权益(或股东权益)合计": 281135886435.69,
    },
]


def test_sina_symbol_maps_market_prefix():
    assert sina_symbol("600519") == "sh600519"
    assert sina_symbol("000001") == "sz000001"
    assert sina_symbol("300750") == "sz300750"


def test_sina_symbol_rejects_beijing_exchange():
    with pytest.raises(ValueError):
        sina_symbol("830799")


def test_parse_balance_sheet_emits_three_indicators_per_period():
    rows = list(parse_balance_sheet(BALANCE_SHEET, symbol="600519"))
    assert len(rows) == 6
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "总资产",
        "indicator_value": 309050784569.31,
    } in rows
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "净资产(归母)",
        "indicator_value": 251253594419.5,
    } in rows
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "净资产(合计)",
        "indicator_value": 262096352174.36,
    } in rows


def test_parse_balance_sheet_skips_nan_column():
    """`所有者权益` 列实测为 NaN，不得产出任何指标行。"""
    records = [{"报告日": "20260630", "所有者权益": math.nan}]
    assert list(parse_balance_sheet(records, symbol="600519")) == []


def test_parse_balance_sheet_skips_missing_indicator():
    records = [{"报告日": "20260630", "资产总计": 100.0}]
    assert list(parse_balance_sheet(records, symbol="600519")) == [
        {
            "symbol": "600519",
            "report_date": "2026-06-30",
            "indicator_name": "总资产",
            "indicator_value": 100.0,
        }
    ]


def test_parse_balance_sheet_skips_malformed_report_date():
    records = [{"报告日": "2026-06-30", "资产总计": 100.0}]
    assert list(parse_balance_sheet(records, symbol="600519")) == []
