"""Eastmoney A-share share structure source (lazy import to keep CLI light)."""
from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Iterator


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


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


def _format_change_date(value: Any) -> str | None:
    """把上游变更日期归一化为 YYYY-MM-DD；无法解析时返回 None（上层跳过）。

    akshare 当前返回 datetime.date，str() 后为 '2026-05-28'；但上游可能改成
    pandas.Timestamp，str() 得 '2026-05-28 00:00:00'，字典序比较会静默出错，
    故在此层显式归一化，与 sina_cn._format_report_date 对称。
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


def fetch_share_structure(code: str) -> list[dict[str, Any]]:
    frame = _ak().stock_zh_a_gbjg_em(symbol=code)
    return frame.to_dict("records")


def parse_share_structure(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        change_date = _format_change_date(record.get("变更日期"))
        total_shares = _to_float(record.get("总股本"))
        if not change_date or total_shares is None:
            continue
        yield {
            "symbol": symbol,
            "change_date": change_date,
            "total_shares": total_shares,
            "float_shares": _to_float(record.get("已流通股份")),
        }
