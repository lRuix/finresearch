"""Eastmoney A-share share structure source (lazy import to keep CLI light)."""
from __future__ import annotations

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


def fetch_share_structure(code: str) -> list[dict[str, Any]]:
    frame = _ak().stock_zh_a_gbjg_em(symbol=code)
    return frame.to_dict("records")


def parse_share_structure(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        change_date = str(record.get("变更日期") or "").strip()
        total_shares = _to_float(record.get("总股本"))
        if not change_date or total_shares is None:
            continue
        yield {
            "symbol": symbol,
            "change_date": change_date,
            "total_shares": total_shares,
            "float_shares": _to_float(record.get("已流通股份")),
        }
