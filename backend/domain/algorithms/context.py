"""AnalysisContext — 工程层传给算法层的干净数据契约。

算法层只消费这个对象，不 import providers、不发起网络请求。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisContext:
    symbol: str
    market: str
    currency: str
    klines: list[dict] = field(default_factory=list)
    macro_bias: float = 55.0
    news_sentiment: float = 0.0
    fx_rate: float | None = None
    horizon: str = "short"
