"""加权合成引擎：截面 z-score → 加权 → 映射 0-100 → 情绪乘数。"""
from __future__ import annotations

import math

from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.factors.base import Factor
from core.algorithms.sentiment.base import SentimentAnalyzer


def _clamp(v: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, v))


def _sigmoid(x: float) -> float:
    # 将 z-score（约 -3..3）映射到 0-100
    return 100 / (1 + math.exp(-x))


class WeightedEngine(RecommendationEngine):
    def __init__(self, factors: list[Factor] | None = None,
                 sentiment: SentimentAnalyzer | None = None,
                 factor_names: list[str] | None = None,
                 weights: dict[str, float] | None = None):
        if factors is None:
            from core.algorithms.factors import FACTOR_REGISTRY
            factors = [FACTOR_REGISTRY[n]() for n in (factor_names or [])]
        if sentiment is None:
            from core.algorithms.sentiment import SENTIMENT_REGISTRY
            sentiment = SENTIMENT_REGISTRY["news_rule"]()
        self._factors = factors
        self._sentiment = sentiment
        self._weights = weights or {f.name: 1.0 / len(factors) for f in factors}

    @property
    def factors(self) -> list[Factor]:
        return self._factors

    @property
    def sentiment(self) -> SentimentAnalyzer:
        return self._sentiment

    def combine(self, factor_scores: dict[str, float], sentiment: dict) -> dict:
        available = {k: v for k, v in factor_scores.items() if k in self._weights}
        if not available:
            return {"total_score": 50.0, "detail": {"available": [], "multiplier": sentiment.get("multiplier", 1.0)}}

        # 截面 z-score（对可用因子得分）
        values = list(available.values())
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        if std < 1e-9:
            z_scores = {k: 0.0 for k in available}
        else:
            z_scores = {k: (v - mean) / std for k, v in available.items()}

        # 加权（用可用因子的权重重新归一化）
        total_w = sum(self._weights.get(k, 0.0) for k in available) or 1.0
        composite_z = sum(z_scores[k] * self._weights.get(k, 0.0) / total_w for k in available)

        base_score = _sigmoid(composite_z)
        multiplier = sentiment.get("multiplier", 1.0)
        total = _clamp(base_score * multiplier)

        return {
            "total_score": round(total, 1),
            "detail": {
                "z_scores": {k: round(v, 4) for k, v in z_scores.items()},
                "available": sorted(available),
                "multiplier": multiplier,
                "base_score": round(base_score, 1),
            },
        }
