"""Gate kline source."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from etl.sources.common import get_json, parse_ts


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _raw_klines(market, symbol, period, limit):
    pair = f"{symbol[:-4]}_{symbol[-4:]}"
    interval_map = {"h": "1h", "d": "1d", "w": "1w"}
    params = urlencode(
        {
            "currency_pair": pair,
            "interval": interval_map[period],
            "limit": limit,
        }
    )
    payload = get_json(
        f"https://api.gateio.ws/api/v4/spot/candlesticks?{params}",
        timeout=8,
    )
    if not payload:
        raise ValueError(f"gate returned no rows for {symbol}")
    rows = []
    for item in payload:
        rows.append(
            {
                "time": datetime.fromtimestamp(
                    int(item[0]), tz=timezone.utc
                ).isoformat(),
                "open": _to_float(item[5]) if len(item) > 5 else 0.0,
                "high": _to_float(item[3]) if len(item) > 3 else 0.0,
                "low": _to_float(item[4]) if len(item) > 4 else 0.0,
                "close": _to_float(item[2]) if len(item) > 2 else 0.0,
                "volume": _to_float(item[6]) if len(item) > 6 else 0.0,
                "quote_volume": _to_float(item[1]) if len(item) > 1 else 0.0,
                "trades_count": _to_float(item[7]) if len(item) > 7 else 0.0,
                "funding_rate": _to_float(item[8]) if len(item) > 8 else 0.0,
            }
        )
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
