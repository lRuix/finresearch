"""Binance kline source."""
from __future__ import annotations

from datetime import datetime, timezone

from etl.sources.common import get_json, parse_ts


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0.0


def _raw_klines(market, symbol, period, limit):
    interval_map = {"h": "1h", "d": "1d", "w": "1w"}
    url = (
        "https://api.binance.com/api/v3/klines"
        f"?symbol={symbol}&interval={interval_map[period]}&limit={limit}"
    )
    payload = get_json(url)
    rows = []
    for item in payload:
        rows.append(
            {
                "time": datetime.fromtimestamp(
                    item[0] / 1000, tz=timezone.utc
                ).isoformat(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "quote_volume": float(item[7]) if len(item) > 7 else 0.0,
                "trades_count": _to_int(item[8]) if len(item) > 8 else 0.0,
            }
        )
    if not rows:
        raise ValueError("binance returned no rows")
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
