"""Factor 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.context import AnalysisContext


class Factor(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def score(self, ctx: AnalysisContext) -> dict:
        """返回 {"score": 0-100, "detail": {...}}"""
