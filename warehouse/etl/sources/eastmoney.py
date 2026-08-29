"""Eastmoney fund kline source."""
from __future__ import annotations

from urllib.parse import urlencode

from etl.sources.common import aggregate_weekly, get_json, parse_ts


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _raw_klines(market, symbol, period, limit):
    if period == "h":
        raise ValueError("fund nav does not provide hourly data")
    params = urlencode(
        {
            "fundCode": symbol,
            "pageIndex": 1,
            "pageSize": min(limit, 200),
        }
    )
    payload = get_json(
        f"https://api.fund.eastmoney.com/f10/lsjz?{params}",
        timeout=8,
        headers={
            "Referer": "https://fundf10.eastmoney.com/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    items = (payload or {}).get("Data", {}).get("LSJZList", [])
    rows = []
    for item in items:
        nav = _to_float(item.get("DWJZ"))
        rows.append(
            {
                "time": str(item.get("FSRQ", "")),
                "nav": nav,
                "accum_nav": _to_float(item.get("LJJZ")),
                "daily_growth_pct": _to_float(item.get("JZZZL")),
                "open": nav,
                "high": nav,
                "low": nav,
                "close": nav,
                "volume": 0.0,
            }
        )
    rows = list(reversed(rows))
    if not rows:
        raise ValueError(f"eastmoney returned no rows for {symbol}")
    if period == "w":
        features = {
            row["time"]: {
                "nav": row["nav"],
                "accum_nav": row["accum_nav"],
                "daily_growth_pct": row["daily_growth_pct"],
            }
            for row in rows
        }
        rows = aggregate_weekly(rows)
        for row in rows:
            row.update(features.get(row["time"], {}))
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
