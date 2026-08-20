"""SentimentAnalyzer 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.context import AnalysisContext


class SentimentAnalyzer(ABC):
    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> dict:
        """返回 {"polarity": -1..1, "confidence": 0..1, "multiplier": 0.8..1.2}"""
