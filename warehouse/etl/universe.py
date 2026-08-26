"""Static universe for markets without a free full-market source."""
from __future__ import annotations


CONFIG_MARKETS = ("us", "kr", "fx")

_STATIC_UNIVERSE = [
    # 美股（无免费全量列表，配置代表标的）
    {"symbol": "AAPL", "name": "Apple", "market": "us", "currency": "USD", "sector": "科技", "base_risk": 0.55, "liquidity": 1.0},
    {"symbol": "NVDA", "name": "NVIDIA", "market": "us", "currency": "USD", "sector": "半导体", "base_risk": 0.8, "liquidity": 1.0},
    {"symbol": "MSFT", "name": "Microsoft", "market": "us", "currency": "USD", "sector": "科技", "base_risk": 0.52, "liquidity": 1.0},
    {"symbol": "TSLA", "name": "Tesla", "market": "us", "currency": "USD", "sector": "汽车", "base_risk": 0.85, "liquidity": 0.98},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "market": "us", "currency": "USD", "sector": "宽基指数", "base_risk": 0.5, "liquidity": 1.0},
    # 韩股（无免费全量列表，配置代表标的）
    {"symbol": "005930.KS", "name": "三星电子", "market": "kr", "currency": "KRW", "sector": "半导体", "base_risk": 0.66, "liquidity": 0.95},
    {"symbol": "000660.KS", "name": "SK海力士", "market": "kr", "currency": "KRW", "sector": "半导体", "base_risk": 0.78, "liquidity": 0.9},
    {"symbol": "035420.KS", "name": "NAVER", "market": "kr", "currency": "KRW", "sector": "互联网", "base_risk": 0.7, "liquidity": 0.82},
    {"symbol": "373220.KS", "name": "LG新能源", "market": "kr", "currency": "KRW", "sector": "新能源", "base_risk": 0.75, "liquidity": 0.85},
    # 外汇（静态主要货币对）
    {"symbol": "USDCNY=X", "name": "美元/人民币", "market": "fx", "currency": "CNY", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "EURUSD=X", "name": "欧元/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.3, "liquidity": 1.0},
    {"symbol": "USDJPY=X", "name": "美元/日元", "market": "fx", "currency": "JPY", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "GBPUSD=X", "name": "英镑/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.32, "liquidity": 1.0},
]


def static_universe() -> list[dict]:
    """美股/韩股配置清单 + 外汇静态清单（无免费全量源的市场走这里）。"""
    return [dict(item) for item in _STATIC_UNIVERSE]


def static_universe_for(market: str) -> list[dict]:
    return [item for item in static_universe() if item["market"] == market]
