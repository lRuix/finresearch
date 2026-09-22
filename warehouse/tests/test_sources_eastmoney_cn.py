"""Eastmoney share structure source tests."""
from __future__ import annotations

from datetime import date, datetime
import math

from pandas import Timestamp

from etl.sources.eastmoney_cn import parse_share_structure


SHARE_STRUCTURE = [
    {
        "变更日期": "2026-05-28",
        "总股本": 1250081601,
        "流通受限股份": 0.0,
        "已流通股份": 1250081601,
        "变动原因": "回购",
    },
    {
        "变更日期": "2025-09-01",
        "总股本": 1252270215,
        "流通受限股份": 0.0,
        "已流通股份": 1252270215,
        "变动原因": "回购",
    },
]


def test_parse_share_structure_maps_real_columns():
    rows = list(parse_share_structure(SHARE_STRUCTURE, symbol="600519"))
    assert rows == [
        {
            "symbol": "600519",
            "change_date": "2026-05-28",
            "total_shares": 1250081601.0,
            "float_shares": 1250081601.0,
        },
        {
            "symbol": "600519",
            "change_date": "2025-09-01",
            "total_shares": 1252270215.0,
            "float_shares": 1252270215.0,
        },
    ]


def test_parse_share_structure_skips_missing_total_shares():
    records = [{"变更日期": "2026-05-28", "总股本": math.nan, "已流通股份": 100.0}]
    assert list(parse_share_structure(records, symbol="600519")) == []


def test_parse_share_structure_keeps_null_float_shares():
    """流通股本缺失时仍保留总股本（总市值可用），float_shares 为 None。"""
    records = [{"变更日期": "2026-05-28", "总股本": 1000.0}]
    assert list(parse_share_structure(records, symbol="600519")) == [
        {
            "symbol": "600519",
            "change_date": "2026-05-28",
            "total_shares": 1000.0,
            "float_shares": None,
        }
    ]


def test_parse_share_structure_skips_missing_change_date():
    records = [{"总股本": 1000.0, "已流通股份": 1000.0}]
    assert list(parse_share_structure(records, symbol="600519")) == []


def test_parse_share_structure_accepts_real_date_types():
    """真实响应形状：akshare 返回 datetime.date（生产路径），亦可能是 pandas.Timestamp。

    夹具必须用真实类型，否则 `_format_change_date` 的 date/datetime 分支零覆盖。
    """
    records = [
        {
            "变更日期": date(2026, 5, 28),
            "总股本": 1250081601,
            "已流通股份": 1250081601,
        },
        {
            "变更日期": datetime(2025, 9, 1, 0, 0),
            "总股本": 1252270215,
            "已流通股份": 1252270215,
        },
        {
            "变更日期": Timestamp("2025-03-31"),
            "总股本": 1000.0,
            "已流通股份": 1000.0,
        },
    ]
    rows = list(parse_share_structure(records, symbol="600519"))
    assert [row["change_date"] for row in rows] == [
        "2026-05-28",
        "2025-09-01",
        "2025-03-31",
    ]
