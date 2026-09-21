"""Eastmoney share structure source tests."""
from __future__ import annotations

import math

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
