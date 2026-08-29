"""Frankfurter kline source."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from etl.sources.common import aggregate_weekly, get_json, parse_ts


def _currency_pair(symbol):
    code = symbol.split("=")[0].replace("/", "")
    if len(code) != 6 or not code.isalpha():
        raise ValueError(f"frankfurter cannot parse symbol {symbol}")
    return code[:3].upper(), code[3:].upper()


def _raw_klines(market, symbol, period, limit):
    if period == "h":
        raise ValueError("frankfurter does not provide hourly fx rates")
    base, quote = _currency_pair(symbol)
    inverse = quote == "USD"
    target = base if inverse else quote
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=min(max(limit * 2, 30), 360))
    payload = get_json(
        f"https://api.frankfurter.dev/v1/{start.isoformat()}..{end.isoformat()}"
        f"?base=USD&symbols={target}",
        timeout=8,
    )
    rates = (payload or {}).get("rates", {})
    rows = []
    previous = None
    for day in sorted(rates.keys()):
        value = float(rates[day][target])
        rate = 1 / value if inverse else value
        close = rate
        open_price = previous if previous is not None else close
        rows.append(
            {
                "time": day,
                "base": base,
                "quote": quote,
                "rate": rate,
                "open": open_price,
                "high": max(open_price, close),
                "low": min(open_price, close),
                "close": close,
                "volume": 0.0,
            }
        )
        previous = close
    if not rows:
        raise ValueError(f"frankfurter returned no rows for {symbol}")
    if period == "w":
        rows = aggregate_weekly(rows)
        for row in rows:
            row.update({"base": base, "quote": quote, "rate": row["close"]})
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
