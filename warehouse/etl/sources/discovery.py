"""Market-wide instrument discovery for the warehouse."""
from __future__ import annotations

import threading
import time
from typing import Any

from etl.sources.common import get_json
from etl.universe import static_universe_for


CACHE_TTL_SECONDS = 300
_discovery_cache: dict[str, tuple[float, list[dict]]] = {}
_discovery_lock = threading.Lock()

_CRYPTO_STABLECOINS = {
    "USDT", "USDC", "BUSD", "TUSD", "DAI", "FDUSD", "EURT", "PYUSD",
}

_MARKET_BASE_RISK = {
    "a-share": 0.62,
    "fund": 0.68,
    "us": 0.62,
    "kr": 0.68,
    "hk": 0.68,
    "fx": 0.35,
    "crypto": 0.86,
}


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def top_frame_candidates(
    frame,
    market: str,
    symbol_col: str,
    name_col: str,
    amount_col: str,
    symbol_fn,
    currency: str,
    sector: str,
) -> list[dict]:
    """从东财风格全市场快照 DataFrame 提取全部标的（按成交额降序）。"""
    import pandas as pd

    if symbol_col not in frame.columns or name_col not in frame.columns or amount_col not in frame.columns:
        raise ValueError(f"{market} snapshot missing columns")
    copy = frame.copy()
    copy[amount_col] = pd.to_numeric(copy[amount_col], errors="coerce").fillna(0)
    copy = copy.sort_values(amount_col, ascending=False)
    rows = []
    for _, row in copy.iterrows():
        code = str(row[symbol_col]).strip()
        if not code.isdigit():
            continue
        rows.append(
            {
                "symbol": symbol_fn(code),
                "name": str(row[name_col]),
                "market": market,
                "currency": currency,
                "sector": sector,
                "base_risk": _MARKET_BASE_RISK.get(market, 0.65),
                "liquidity": 0.85,
            }
        )
    return rows


def a_share_candidates() -> list[dict]:
    return top_frame_candidates(
        _ak().stock_zh_a_spot_em(),
        "a-share",
        "代码",
        "名称",
        "成交额",
        lambda code: code.zfill(6),
        "CNY",
        "未分类",
    )


def hk_candidates() -> list[dict]:
    return top_frame_candidates(
        _ak().stock_hk_spot_em(),
        "hk",
        "代码",
        "名称",
        "成交额",
        lambda code: f"{code.zfill(5)}.HK",
        "HKD",
        "未分类",
    )


def fund_candidates() -> list[dict]:
    return top_frame_candidates(
        _ak().fund_etf_spot_em(),
        "fund",
        "代码",
        "名称",
        "成交额",
        lambda code: code.zfill(6),
        "CNY",
        "场内基金",
    )


def crypto_candidates() -> list[dict]:
    payload = get_json("https://api.gateio.ws/api/v4/spot/tickers")
    pairs: list[tuple[float, str]] = []
    for item in payload:
        pair = str(item.get("currency_pair", ""))
        if not pair.endswith("_USDT"):
            continue
        base = pair.split("_")[0]
        if base in _CRYPTO_STABLECOINS:
            continue
        try:
            volume = float(item.get("quote_volume", 0) or 0)
        except (TypeError, ValueError):
            volume = 0.0
        pairs.append((volume, base))
    pairs.sort(reverse=True)
    return [
        {
            "symbol": f"{base}USDT",
            "name": base,
            "market": "crypto",
            "currency": "USDT",
            "sector": "数字资产",
            "base_risk": _MARKET_BASE_RISK["crypto"],
            "liquidity": 0.9,
        }
        for _, base in pairs
    ]


def discover_dynamic(market: str) -> list[dict]:
    if market == "a-share":
        return a_share_candidates()
    if market == "hk":
        return hk_candidates()
    if market == "fund":
        return fund_candidates()
    if market == "crypto":
        return crypto_candidates()
    if market == "fx":
        return static_universe_for("fx")
    raise ValueError(f"no dynamic discovery for market: {market}")


def discover_instruments(market: str) -> list[dict]:
    """返回某市场全量标的：静态配置市场读静态清单，其余动态发现。"""
    if market in ("us", "kr", "fx"):
        return static_universe_for(market)
    key = f"discover:{market}"
    with _discovery_lock:
        cached = _discovery_cache.get(key)
        if cached is not None and cached[0] > time.time():
            return [dict(item) for item in cached[1]]
    rows = discover_dynamic(market)
    with _discovery_lock:
        _discovery_cache[key] = (time.time() + CACHE_TTL_SECONDS, [dict(item) for item in rows])
    return rows
