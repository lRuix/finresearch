"""Data source response parsing helpers."""
from __future__ import annotations

from datetime import datetime, timezone


def _is_blank(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip() or value.strip().lower() == "none"
    return False


def _to_iso_timestamp(value: object) -> str | None:
    if value is None or _is_blank(value):
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    if timestamp < 0 or timestamp > 10_000_000_000_000:
        return None
    if timestamp >= 100_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if value is None or _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None or _is_blank(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def parse_binance_klines(raw: list[list[object]]) -> list[dict[str, object]]:
    """Parse Binance /api/v3/klines rows into normalized OHLCV dicts."""
    rows: list[dict[str, object]] = []
    for item in raw:
        rows.append({
            "time": _to_iso_timestamp(item[0] if len(item) > 0 else None),
            "open": _to_float(item[1] if len(item) > 1 else None),
            "high": _to_float(item[2] if len(item) > 2 else None),
            "low": _to_float(item[3] if len(item) > 3 else None),
            "close": _to_float(item[4] if len(item) > 4 else None),
            "volume": _to_float(item[5] if len(item) > 5 else None),
            "quote_volume": _to_float(item[7] if len(item) > 7 else None),
            "trades_count": _to_int(item[8] if len(item) > 8 else None),
            "raw": item,
        })
    return rows


def parse_gate_klines(raw: list[list[object]]) -> list[dict[str, object]]:
    """Parse Gate /spot/candlesticks rows into normalized OHLCV dicts."""
    rows: list[dict[str, object]] = []
    for item in raw:
        rows.append({
            "time": _to_iso_timestamp(item[0] if len(item) > 0 else None),
            "quote_volume": _to_float(item[1] if len(item) > 1 else None),
            "close": _to_float(item[2] if len(item) > 2 else None),
            "high": _to_float(item[3] if len(item) > 3 else None),
            "low": _to_float(item[4] if len(item) > 4 else None),
            "open": _to_float(item[5] if len(item) > 5 else None),
            "volume": _to_float(item[6] if len(item) > 6 else None),
            "raw": item,
        })
    return rows


def parse_eastmoney_fund(item: dict[str, object]) -> dict[str, object]:
    """Parse one Eastmoney LSJZList item into a normalized fund NAV dict."""
    return {
        "ts": _to_str(item.get("FSRQ")),
        "nav": _to_float(item.get("DWJZ")),
        "accum_nav": _to_float(item.get("LJJZ")),
        "daily_growth_pct": _to_float(item.get("JZZZL")),
        "purchase_status": _to_str(item.get("SGZT")),
        "redeem_status": _to_str(item.get("SHZT")),
        "raw": item,
    }
