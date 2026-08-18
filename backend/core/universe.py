"""Universe definitions for all supported markets."""

from __future__ import annotations

MARKETS = [
    {
        "id": "a-share",
        "name": "A股",
        "region": "CN",
        "currency": "CNY",
        "trading_hours": "09:30-15:00",
    },
    {
        "id": "fund",
        "name": "基金",
        "region": "CN",
        "currency": "CNY",
        "trading_hours": "09:30-15:00",
    },
    {
        "id": "us",
        "name": "美股",
        "region": "US",
        "currency": "USD",
        "trading_hours": "22:30-05:00",
    },
    {
        "id": "kr",
        "name": "韩股",
        "region": "KR",
        "currency": "KRW",
        "trading_hours": "09:00-15:30",
    },
    {
        "id": "hk",
        "name": "港股",
        "region": "HK",
        "currency": "HKD",
        "trading_hours": "09:30-16:00",
    },
    {
        "id": "fx",
        "name": "外汇",
        "region": "GLOBAL",
        "currency": "MULTI",
        "trading_hours": "24H",
    },
    {
        "id": "crypto",
        "name": "数字货币",
        "region": "GLOBAL",
        "currency": "USDT",
        "trading_hours": "24H",
    },
]

UNIVERSE = [
    # A 股
    {"symbol": "600519", "name": "贵州茅台", "market": "a-share", "currency": "CNY", "sector": "消费", "base_risk": 0.62, "liquidity": 0.95},
    {"symbol": "000001", "name": "平安银行", "market": "a-share", "currency": "CNY", "sector": "银行", "base_risk": 0.58, "liquidity": 0.92},
    {"symbol": "300750", "name": "宁德时代", "market": "a-share", "currency": "CNY", "sector": "新能源", "base_risk": 0.74, "liquidity": 0.9},
    {"symbol": "601318", "name": "中国平安", "market": "a-share", "currency": "CNY", "sector": "保险", "base_risk": 0.6, "liquidity": 0.9},
    {"symbol": "600036", "name": "招商银行", "market": "a-share", "currency": "CNY", "sector": "银行", "base_risk": 0.55, "liquidity": 0.93},
    # 基金
    {"symbol": "110022", "name": "易方达消费行业", "market": "fund", "currency": "CNY", "sector": "消费主题", "base_risk": 0.7, "liquidity": 0.8},
    {"symbol": "161725", "name": "招商中证白酒", "market": "fund", "currency": "CNY", "sector": "消费主题", "base_risk": 0.75, "liquidity": 0.78},
    {"symbol": "510300", "name": "沪深300ETF", "market": "fund", "currency": "CNY", "sector": "宽基指数", "base_risk": 0.6, "liquidity": 0.94},
    {"symbol": "159915", "name": "创业板ETF", "market": "fund", "currency": "CNY", "sector": "宽基指数", "base_risk": 0.72, "liquidity": 0.9},
    # 美股
    {"symbol": "AAPL", "name": "Apple", "market": "us", "currency": "USD", "sector": "科技", "base_risk": 0.55, "liquidity": 1.0},
    {"symbol": "NVDA", "name": "NVIDIA", "market": "us", "currency": "USD", "sector": "半导体", "base_risk": 0.8, "liquidity": 1.0},
    {"symbol": "MSFT", "name": "Microsoft", "market": "us", "currency": "USD", "sector": "科技", "base_risk": 0.52, "liquidity": 1.0},
    {"symbol": "TSLA", "name": "Tesla", "market": "us", "currency": "USD", "sector": "汽车", "base_risk": 0.85, "liquidity": 0.98},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "market": "us", "currency": "USD", "sector": "宽基指数", "base_risk": 0.5, "liquidity": 1.0},
    # 韩股
    {"symbol": "005930.KS", "name": "三星电子", "market": "kr", "currency": "KRW", "sector": "半导体", "base_risk": 0.66, "liquidity": 0.95},
    {"symbol": "000660.KS", "name": "SK海力士", "market": "kr", "currency": "KRW", "sector": "半导体", "base_risk": 0.78, "liquidity": 0.9},
    {"symbol": "035420.KS", "name": "NAVER", "market": "kr", "currency": "KRW", "sector": "互联网", "base_risk": 0.7, "liquidity": 0.82},
    {"symbol": "373220.KS", "name": "LG新能源", "market": "kr", "currency": "KRW", "sector": "新能源", "base_risk": 0.75, "liquidity": 0.85},
    # 港股
    {"symbol": "0700.HK", "name": "腾讯控股", "market": "hk", "currency": "HKD", "sector": "互联网", "base_risk": 0.68, "liquidity": 0.96},
    {"symbol": "9988.HK", "name": "阿里巴巴-W", "market": "hk", "currency": "HKD", "sector": "互联网", "base_risk": 0.72, "liquidity": 0.95},
    {"symbol": "3690.HK", "name": "美团-W", "market": "hk", "currency": "HKD", "sector": "本地生活", "base_risk": 0.76, "liquidity": 0.9},
    {"symbol": "1810.HK", "name": "小米集团-W", "market": "hk", "currency": "HKD", "sector": "消费电子", "base_risk": 0.7, "liquidity": 0.92},
    # 外汇
    {"symbol": "USDCNY=X", "name": "美元/人民币", "market": "fx", "currency": "CNY", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "EURUSD=X", "name": "欧元/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.3, "liquidity": 1.0},
    {"symbol": "USDJPY=X", "name": "美元/日元", "market": "fx", "currency": "JPY", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "GBPUSD=X", "name": "英镑/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.32, "liquidity": 1.0},
    # 数字货币
    {"symbol": "BTCUSDT", "name": "Bitcoin", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.85, "liquidity": 1.0},
    {"symbol": "ETHUSDT", "name": "Ethereum", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.9, "liquidity": 0.98},
    {"symbol": "SOLUSDT", "name": "Solana", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.95, "liquidity": 0.92},
    {"symbol": "BNBUSDT", "name": "BNB", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.88, "liquidity": 0.9},
]

MARKET_NAMES = {m["id"]: m["name"] for m in MARKETS}


def find_symbol(market: str, symbol: str) -> dict | None:
    for item in UNIVERSE:
        if item["market"] == market and item["symbol"] == symbol:
            return item
    return None


def universe_for(market: str) -> list[dict]:
    if market in ("all", "", None):
        return UNIVERSE
    return [item for item in UNIVERSE if item["market"] == market]
