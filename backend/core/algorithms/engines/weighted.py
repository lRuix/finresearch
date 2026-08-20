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
        """单标的合成：对单个标的的 5 个因子做横向 z-score。

        注意语义：此处 z-score 是「因子间相对强弱」（衡量各因子均衡度），
        不是 spec 5.4 要求的「跨标的同市场截面」绝对强弱——后者请用
        score_cross_sectional（对同一因子在所有标的间做 z-score）。
        """
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

    def score_cross_sectional(self, contexts: list[AnalysisContext]) -> list[dict]:
        """跨标的同市场截面评分：对每个因子在同市场所有标的间做 z-score。

        contexts: 同一市场的标的上下文列表（每个含 symbol + klines 等）。
        返回每个标的的评分 dict（含 symbol、因子原始分、因子 z-score、总分）。
        """
        from core.algorithms.context import AnalysisContext

        # 1) 算每个标的的因子原始分
        per_symbol: dict[str, dict[str, float]] = {}
        for ctx in contexts:
            scores = {}
            for factor in self.factors:
                result = factor.score(ctx)
                scores[factor.name] = result["score"]
            per_symbol[ctx.symbol] = scores

        # 2) 对每个因子，在标的间做 z-score
        factor_names = [f.name for f in self.factors]
        z_per_symbol: dict[str, dict[str, float]] = {ctx.symbol: {} for ctx in contexts}
        for fname in factor_names:
            raw = [per_symbol[s][fname] for s in per_symbol]
            mean = sum(raw) / len(raw) if raw else 0.0
            var = sum((v - mean) ** 2 for v in raw) / len(raw) if raw else 0.0
            std = var ** 0.5
            for ctx in contexts:
                s = ctx.symbol
                z_per_symbol[s][fname] = (per_symbol[s][fname] - mean) / std if std > 1e-9 else 0.0

        # 3) 每个标的：加权合成 z-score → sigmoid → 情绪乘数
        results = []
        for ctx in contexts:
            s = ctx.symbol
            sentiment = self.sentiment.analyze(ctx)
            total_w = sum(self._weights.get(f, 0.0) for f in factor_names) or 1.0
            composite_z = sum(
                z_per_symbol[s][f] * self._weights.get(f, 0.0) / total_w
                for f in factor_names
            )
            base_score = _sigmoid(composite_z)
            multiplier = sentiment.get("multiplier", 1.0)
            total = _clamp(base_score * multiplier)
            results.append({
                "symbol": s,
                "market": ctx.market,
                "factor_scores": per_symbol[s],
                "factor_z_scores": {f: round(z_per_symbol[s][f], 4) for f in factor_names},
                "total_score": round(total, 1),
                "base_score": round(base_score, 1),
                "multiplier": multiplier,
            })
        return results
