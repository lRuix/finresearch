"""RecommendationEngine 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.factors.base import Factor
from core.algorithms.sentiment.base import SentimentAnalyzer


class RecommendationEngine(ABC):
    @property
    @abstractmethod
    def factors(self) -> list[Factor]: ...

    @property
    @abstractmethod
    def sentiment(self) -> SentimentAnalyzer: ...

    @abstractmethod
    def combine(self, factor_scores: dict[str, float], sentiment: dict) -> dict:
        """返回 {"total_score": 0-100, "detail": {...}}"""
