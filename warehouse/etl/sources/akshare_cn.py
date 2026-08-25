"""akshare China A-share fetchers and parsers (lazy import to keep CLI light)."""
from __future__ import annotations

from typing import Any, Iterator


FINANCIAL_INDICATORS = ("净利润", "净利润同比增长率", "扣非净利润", "营业总收入")


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def fetch_financials(symbol: str) -> list[dict[str, Any]]:
    frame = _ak().stock_financial_abstract_ths(symbol=symbol)
    return frame.to_dict("records")


def fetch_lhb(start_date: str, end_date: str) -> list[dict[str, Any]]:
    frame = _ak().stock_lhb_detail_em(start_date=start_date, end_date=end_date)
    return frame.to_dict("records")


def parse_financials(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        report_date = record.get("报告期")
        for indicator in FINANCIAL_INDICATORS:
            value = record.get(indicator)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            yield {
                "symbol": symbol,
                "report_date": str(report_date),
                "indicator_name": indicator,
                "indicator_value": numeric,
            }


def parse_lhb(records: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for record in records:
        yield {
            "trade_date": str(record["上榜日"]),
            "code": str(record["代码"]),
            "name": str(record["名称"]),
            "close_price": _to_float(record.get("收盘价")),
            "change_pct": _to_float(record.get("涨跌幅")),
            "reason": str(record.get("解读") or ""),
        }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
