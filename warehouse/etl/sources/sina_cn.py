"""Sina A-share balance sheet source (lazy import to keep CLI light)."""
from __future__ import annotations

import math
from datetime import date, datetime
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
    """A 股 6 位代码转新浪带前缀代码。

    前缀规则：首位 6 或 9 → `sh`，首位 0 或 3 → `sz`，其余（北交所 4/8 段）抛错。

    实测：`920xxx`（北交所新代码段，首位 9）被映射为 `sh920xxx`，新浪按纯数字
    解析该代码可用——`ods_cn_balance` 中已有 345 只 920xxx（31,088 行）真实数据
    经此路径入库。故 9 段不做北交所排除，**不得**改为抛错（`8xxxxx`/`4xxxxx`
    仍抛错）。
    """
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
    """把上游报告日归一化为 YYYY-MM-DD；无法解析时返回 None（上层跳过）。

    实测上游返回 8 位数字串（'20260630'）；但 date/datetime/ISO 字符串同样要
    归一化——只认一种格式意味着上游一改格式，整只标的的报告期会被静默丢行。
    归一化口径与 eastmoney_cn._format_change_date 保持一致。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():  # YYYYMMDD
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        # 兼容 'YYYY-MM-DD' 与 'YYYY-MM-DD HH:MM:SS'
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


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
