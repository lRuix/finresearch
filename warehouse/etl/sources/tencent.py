"""Tencent kline source."""
from __future__ import annotations

from urllib.parse import urlencode

from etl.sources.common import get_json, parse_ts


def _tencent_symbol(symbol: str, market: str) -> str:
    code = symbol.split(".")[0]
    if market == "a-share":
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return f"{prefix}{code}"
    if market == "fund":
        prefix = "sh" if code.startswith("5") else "sz"
        return f"{prefix}{code}"
    if market == "us":
        return f"us{code}.OQ"
    if market == "hk":
        return f"hk{code.zfill(5)}"
    raise ValueError(f"tencent does not support market {market}")


def _raw_klines(market, symbol, period, limit):
    t_symbol = _tencent_symbol(symbol, market)
    interval = {"h": "m60", "d": "day", "w": "week"}[period]
    adjust = "qfq" if market in ("a-share", "fund") else ""
    params = urlencode({"param": f"{t_symbol},{interval},,,{limit},{adjust}"})
    payload = get_json(
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{params}",
        timeout=6,
        headers={"Referer": "https://gu.qq.com/"},
    )
    node = (payload or {}).get("data", {}).get(t_symbol, {})
    raw_rows = node.get(f"qfq{interval}") or node.get(interval) or []
    if not raw_rows:
        raise ValueError(f"tencent returned no rows for {t_symbol}")
    rows = []
    for item in raw_rows:
        if len(item) < 5:
            continue
        timestamp = str(item[0])
        if period == "h" and " " in timestamp:
            timestamp = timestamp.replace(" ", "T") + ":00"
        rows.append(
            {
                "time": timestamp,
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]) if len(item) > 5 else 0.0,
            }
        )
    if period == "h" and len(rows) < 2:
        raise ValueError("tencent returned insufficient hourly rows")
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
