"""新闻情绪规则：乘数 = 1 + 0.2 * polarity。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.sentiment.base import SentimentAnalyzer


def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


class NewsRuleAnalyzer(SentimentAnalyzer):
    def analyze(self, ctx: AnalysisContext) -> dict:
        polarity = _clamp(ctx.news_sentiment, -1.0, 1.0)
        multiplier = round(1 + 0.2 * polarity, 4)
        return {
            "polarity": round(polarity, 4),
            "confidence": 0.6,
            "multiplier": multiplier,
        }
