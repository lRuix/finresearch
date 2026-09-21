"""Sina A-share balance sheet source (lazy import to keep CLI light)."""
from __future__ import annotations

import math
from typing import Any, Iterator


BALANCE_COLUMNS = (
    ("资产总计", "总资产"),
    ("归属于母公司股东权益合计", "净资产(归母)"),
    ("所有者权益(或股东权益)合计", "净资产(合计)"),
)


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def sina_symbol(code: str) -> str:
    """A 股 6 位代码转新浪带前缀代码；北交所不支持。"""
    text = str(code).strip()
    if text.startswith(("6", "9")):
        return f"sh{text}"
    if text.startswith(("0", "3")):
        return f"sz{text}"
    raise ValueError(f"sina does not support A-share code: {code}")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _format_report_date(value: Any) -> str | None:
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def fetch_balance_sheet(code: str) -> list[dict[str, Any]]:
    frame = _ak().stock_financial_report_sina(
        stock=sina_symbol(code), symbol="资产负债表"
    )
    return frame.to_dict("records")


def parse_balance_sheet(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        report_date = _format_report_date(record.get("报告日"))
        if report_date is None:
            continue
        for column, indicator in BALANCE_COLUMNS:
            value = _to_float(record.get(column))
            if value is None:
                continue
            yield {
                "symbol": symbol,
                "report_date": report_date,
                "indicator_name": indicator,
                "indicator_value": value,
            }
