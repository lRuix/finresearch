"""yfinance kline source."""
from __future__ import annotations

from datetime import timezone

from etl.sources.common import parse_ts


def _yf():
    import yfinance

    return yfinance


def _to_float(value, default=0.0):
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result


def _raw_klines(market, symbol, period, limit):
    ticker = f"{symbol[:-4]}-USD" if market == "crypto" else symbol
    period_map = {
        "h": "3mo" if limit <= 500 else "6mo",
        "d": "3mo" if limit <= 90 else "6mo" if limit <= 180 else "1y",
        "w": "2y",
    }
    interval_map = {"h": "60m", "d": "1d", "w": "1wk"}
    frame = _yf().Ticker(ticker).history(
        period=period_map[period],
        interval=interval_map[period],
        auto_adjust=False,
        actions=True,
        timeout=8,
    )
    if frame.empty:
        raise ValueError(f"yfinance returned no rows for {ticker}")
    rows = []
    for index, row in frame.iterrows():
        timestamp = index.to_pydatetime()
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        close = _to_float(row.get("Close"))
        rows.append(
            {
                "time": timestamp.isoformat(),
                "open": _to_float(row.get("Open")),
                "high": _to_float(row.get("High")),
                "low": _to_float(row.get("Low")),
                "close": close,
                "volume": _to_float(row.get("Volume")),
                "adj_close": _to_float(
                    row.get("Adj Close"), default=close
                ),
                "dividends": _to_float(row.get("Dividends")),
                "stock_splits": _to_float(row.get("Stock Splits")),
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
