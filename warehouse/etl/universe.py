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
    # A 股（东财全市场接口不可达时的代表性标的）
    {"symbol": "600519", "name": "贵州茅台", "market": "a-share", "currency": "CNY", "sector": "消费", "base_risk": 0.62, "liquidity": 0.95},
    {"symbol": "000001", "name": "平安银行", "market": "a-share", "currency": "CNY", "sector": "银行", "base_risk": 0.58, "liquidity": 0.92},
    {"symbol": "300750", "name": "宁德时代", "market": "a-share", "currency": "CNY", "sector": "新能源", "base_risk": 0.74, "liquidity": 0.9},
    {"symbol": "601318", "name": "中国平安", "market": "a-share", "currency": "CNY", "sector": "保险", "base_risk": 0.6, "liquidity": 0.9},
    {"symbol": "600036", "name": "招商银行", "market": "a-share", "currency": "CNY", "sector": "银行", "base_risk": 0.55, "liquidity": 0.93},
    # 基金（代表性场内/场外基金）
    {"symbol": "110022", "name": "易方达消费行业", "market": "fund", "currency": "CNY", "sector": "消费主题", "base_risk": 0.7, "liquidity": 0.8},
    {"symbol": "161725", "name": "招商中证白酒", "market": "fund", "currency": "CNY", "sector": "消费主题", "base_risk": 0.75, "liquidity": 0.78},
    {"symbol": "510300", "name": "沪深300ETF", "market": "fund", "currency": "CNY", "sector": "宽基指数", "base_risk": 0.6, "liquidity": 0.94},
    {"symbol": "159915", "name": "创业板ETF", "market": "fund", "currency": "CNY", "sector": "宽基指数", "base_risk": 0.72, "liquidity": 0.9},
    # 港股（腾讯行情主源）
    {"symbol": "0700.HK", "name": "腾讯控股", "market": "hk", "currency": "HKD", "sector": "互联网", "base_risk": 0.68, "liquidity": 0.96},
    {"symbol": "9988.HK", "name": "阿里巴巴-W", "market": "hk", "currency": "HKD", "sector": "互联网", "base_risk": 0.72, "liquidity": 0.95},
    {"symbol": "3690.HK", "name": "美团-W", "market": "hk", "currency": "HKD", "sector": "本地生活", "base_risk": 0.76, "liquidity": 0.9},
    {"symbol": "1810.HK", "name": "小米集团-W", "market": "hk", "currency": "HKD", "sector": "消费电子", "base_risk": 0.7, "liquidity": 0.92},
    # 外汇（静态主要货币对全列表）
    {"symbol": "USDCNY=X", "name": "美元/人民币", "market": "fx", "currency": "CNY", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "USDHKD=X", "name": "美元/港币", "market": "fx", "currency": "HKD", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "USDKRW=X", "name": "美元/韩元", "market": "fx", "currency": "KRW", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "USDJPY=X", "name": "美元/日元", "market": "fx", "currency": "JPY", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "USDSGD=X", "name": "美元/新加坡元", "market": "fx", "currency": "SGD", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "USDINR=X", "name": "美元/印度卢比", "market": "fx", "currency": "INR", "sector": "主要货币对", "base_risk": 0.45, "liquidity": 1.0},
    {"symbol": "USDTHB=X", "name": "美元/泰铢", "market": "fx", "currency": "THB", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "USDMXN=X", "name": "美元/墨西哥比索", "market": "fx", "currency": "MXN", "sector": "主要货币对", "base_risk": 0.5, "liquidity": 1.0},
    {"symbol": "USDZAR=X", "name": "美元/南非兰特", "market": "fx", "currency": "ZAR", "sector": "主要货币对", "base_risk": 0.5, "liquidity": 1.0},
    {"symbol": "USDBRL=X", "name": "美元/巴西雷亚尔", "market": "fx", "currency": "BRL", "sector": "主要货币对", "base_risk": 0.5, "liquidity": 1.0},
    {"symbol": "USDCAD=X", "name": "美元/加元", "market": "fx", "currency": "CAD", "sector": "主要货币对", "base_risk": 0.35, "liquidity": 1.0},
    {"symbol": "USDCHF=X", "name": "美元/瑞郎", "market": "fx", "currency": "CHF", "sector": "主要货币对", "base_risk": 0.3, "liquidity": 1.0},
    {"symbol": "USDNOK=X", "name": "美元/挪威克朗", "market": "fx", "currency": "NOK", "sector": "主要货币对", "base_risk": 0.45, "liquidity": 1.0},
    {"symbol": "USDSEK=X", "name": "美元/瑞典克朗", "market": "fx", "currency": "SEK", "sector": "主要货币对", "base_risk": 0.45, "liquidity": 1.0},
    {"symbol": "USDDKK=X", "name": "美元/丹麦克朗", "market": "fx", "currency": "DKK", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "USDPLN=X", "name": "美元/波兰兹罗提", "market": "fx", "currency": "PLN", "sector": "主要货币对", "base_risk": 0.45, "liquidity": 1.0},
    {"symbol": "USDTRY=X", "name": "美元/土耳其里拉", "market": "fx", "currency": "TRY", "sector": "主要货币对", "base_risk": 0.6, "liquidity": 1.0},
    {"symbol": "EURUSD=X", "name": "欧元/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.3, "liquidity": 1.0},
    {"symbol": "GBPUSD=X", "name": "英镑/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.32, "liquidity": 1.0},
    {"symbol": "AUDUSD=X", "name": "澳元/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    {"symbol": "NZDUSD=X", "name": "纽元/美元", "market": "fx", "currency": "USD", "sector": "主要货币对", "base_risk": 0.4, "liquidity": 1.0},
    # 加密（Gate 行情主源）
    {"symbol": "BTCUSDT", "name": "Bitcoin", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.85, "liquidity": 1.0},
    {"symbol": "ETHUSDT", "name": "Ethereum", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.9, "liquidity": 0.98},
    {"symbol": "SOLUSDT", "name": "Solana", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.95, "liquidity": 0.92},
    {"symbol": "BNBUSDT", "name": "BNB", "market": "crypto", "currency": "USDT", "sector": "数字资产", "base_risk": 0.88, "liquidity": 0.9},
]


def static_universe() -> list[dict]:
    """美股/韩股配置清单 + 外汇静态清单（无免费全量源的市场走这里）。"""
    return [dict(item) for item in _STATIC_UNIVERSE]


def static_universe_for(market: str) -> list[dict]:
    return [item for item in static_universe() if item["market"] == market]
