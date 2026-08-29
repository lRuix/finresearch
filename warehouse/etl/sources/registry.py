"""Kline source registry and orchestration."""
from __future__ import annotations

import os
from typing import Any, Callable

from etl.sources import (
    akshare,
    binance,
    eastmoney,
    frankfurter,
    gate,
    naver,
    tencent,
    yfinance,
)
from etl.sources.common import cache_get, cache_set, try_provider


SourceFn = Callable[..., list[dict[str, Any]]]


def _fund_chain(symbol: str) -> list[tuple[str, SourceFn]]:
    is_open_fund = not symbol.startswith(("15", "51"))
    if is_open_fund:
        return [
            ("eastmoney", eastmoney.fetch_klines),
            ("tencent", tencent.fetch_klines),
            ("akshare", akshare.fetch_klines),
        ]
    return [
        ("tencent", tencent.fetch_klines),
        ("eastmoney", eastmoney.fetch_klines),
        ("akshare", akshare.fetch_klines),
    ]


SOURCE_CHAINS: dict[str, list[tuple[str, SourceFn]]] = {
    "a-share": [("tencent", tencent.fetch_klines), ("akshare", akshare.fetch_klines)],
    "us": [("tencent", tencent.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "kr": [("naver", naver.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "hk": [("tencent", tencent.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "fx": [("frankfurter", frankfurter.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "crypto": [("gate", gate.fetch_klines), ("binance", binance.fetch_klines), ("yfinance", yfinance.fetch_klines)],
}


def enabled_sources(market: str, symbol: str) -> list[tuple[str, SourceFn]]:
    disabled = {
        item.strip()
        for item in os.environ.get("WAREHOUSE_SOURCE_DISABLED", "").split(",")
        if item.strip()
    }
    chain = _fund_chain(symbol) if market == "fund" else SOURCE_CHAINS.get(market, [])
    return [(name, fn) for name, fn in chain if name not in disabled]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    chain = enabled_sources(market, symbol)
    source_names = ",".join(name for name, _ in chain)
    key = f"{market}:{symbol}:{period}:{limit}:{source_names}"
    cached = cache_get(key)
    if cached is not None:
        rows, _ = cached
        if start:
            rows = [r for r in rows if r["time"] >= start]
        if end:
            rows = [r for r in rows if r["time"] <= end]
        return rows

    for name, fn in chain:
        rows = try_provider(name, key, fn, market, symbol, period, start, end, limit)
        if rows:
            cache_set(key, rows, "live")
            return rows
    return []


def discover_instruments(market: str) -> list[dict[str, Any]]:
    from etl.sources import discovery

    return discovery.discover_instruments(market)
