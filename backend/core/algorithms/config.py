"""算法配置：注册表 → 工厂函数。"""
from __future__ import annotations

from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.engines.weighted import WeightedEngine
from core.algorithms.factors import FACTOR_REGISTRY
from core.algorithms.sentiment import SENTIMENT_REGISTRY

ENGINE_REGISTRY: dict[str, type[RecommendationEngine]] = {
    "weighted": WeightedEngine,
}

DEFAULT_CONFIG = {
    "engine": "weighted",
    "factors": ["trend", "momentum", "volatility", "risk", "macro"],
    "sentiment": "news_rule",
    "weights": {"trend": 0.30, "momentum": 0.25, "volatility": 0.15,
                "risk": 0.15, "macro": 0.15},
}


def build_engine(config: dict | None = None) -> RecommendationEngine:
    cfg = config or DEFAULT_CONFIG
    factor_names = cfg["factors"]
    factors = [FACTOR_REGISTRY[n]() for n in factor_names]
    sentiment = SENTIMENT_REGISTRY[cfg["sentiment"]]()
    engine_cls = ENGINE_REGISTRY[cfg["engine"]]
    if engine_cls is WeightedEngine:
        return WeightedEngine(factors, sentiment, weights=cfg.get("weights"))
    return engine_cls(factors, sentiment)
