"""Sina balance sheet source tests."""
from __future__ import annotations

import math
from datetime import date, datetime

import pytest
from pandas import Timestamp

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


def test_sina_symbol_maps_920_codes_to_sh_prefix():
    """实测：920xxx（北交所新代码段）走 sh 前缀，新浪按数字解析可用。

    ods_cn_balance 中已有 345 只 920xxx（31,088 行）真实数据经该路径入库，
    故此处钉住现状，不得改为抛错。
    """
    assert sina_symbol("920000") == "sh920000"
    assert sina_symbol("920116") == "sh920116"


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


def test_parse_balance_sheet_attributes_rows_to_their_own_period():
    """第二期三条必须带自己的 report_date，避免"全部归到首期"的静默错归因。

    report_date 是 ods_cn_balance 主键的一部分，错归因会静默污染全表。
    """
    rows = list(parse_balance_sheet(BALANCE_SHEET, symbol="600519"))
    assert rows[3:] == [
        {
            "symbol": "600519",
            "report_date": "2026-03-31",
            "indicator_name": "总资产",
            "indicator_value": 319918844905.58,
        },
        {
            "symbol": "600519",
            "report_date": "2026-03-31",
            "indicator_name": "净资产(归母)",
            "indicator_value": 270894035676.27,
        },
        {
            "symbol": "600519",
            "report_date": "2026-03-31",
            "indicator_name": "净资产(合计)",
            "indicator_value": 281135886435.69,
        },
    ]


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
    records = [{"报告日": "2026/06/30", "资产总计": 100.0}]
    assert list(parse_balance_sheet(records, symbol="600519")) == []


def test_parse_balance_sheet_normalizes_native_date_and_iso_report_date():
    """上游若把报告日改成 date/datetime/ISO，也必须归一化而不是静默丢行。

    当前实测为 8 位数字串（'20260630'）；只认该格式意味着上游一改格式就
    整只标的的报告期全部丢行，而且不会报错。
    """
    records = [
        {"报告日": date(2026, 6, 30), "资产总计": 1.0},
        {"报告日": datetime(2026, 3, 31, 0, 0), "资产总计": 2.0},
        {"报告日": "2025-12-31", "资产总计": 3.0},
        {"报告日": Timestamp("2025-09-30"), "资产总计": 4.0},
    ]
    rows = list(parse_balance_sheet(records, symbol="600519"))
    assert [row["report_date"] for row in rows] == [
        "2026-06-30",
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
    ]
