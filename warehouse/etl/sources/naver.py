"""Naver kline source."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from etl.sources.common import get_text, parse_ts


def _raw_klines(market, symbol, period, limit):
    if period == "h":
        raise ValueError("naver does not provide hourly klines")
    timeframe = {"d": "day", "w": "week"}[period]
    code = symbol.split(".")[0]
    text = get_text(
        f"https://fchart.stock.naver.com/sise.nhn?symbol={code}"
        f"&timeframe={timeframe}&count={limit}&requestType=0",
        encoding="euc-kr",
        timeout=8,
    )
    root = ET.fromstring(text)
    rows = []
    for item in root.iter("item"):
        values = item.attrib.get("data", "").split("|")
        if len(values) < 5:
            continue
        raw_date = values[0]
        normalized_date = (
            f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            if len(raw_date) == 8
            else raw_date
        )
        rows.append(
            {
                "time": normalized_date,
                "open": float(values[1]),
                "high": float(values[2]),
                "low": float(values[3]),
                "close": float(values[4]),
                "volume": float(values[5]) if len(values) > 5 else 0.0,
            }
        )
    if not rows:
        raise ValueError(f"naver returned no rows for {symbol}")
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
