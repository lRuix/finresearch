"""趋势因子：均线多头排列 + MACD 柱。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import macd, sma


class TrendFactor(Factor):
    name = "trend"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        if not closes:
            return {"score": 50.0, "detail": {"points": 0, "checks": 0, "empty": True}}
        points = 0
        checks = 0
        sma5, sma10, sma20 = sma(closes, 5), sma(closes, 10), sma(closes, 20)
        sma60 = sma(closes, 60)
        price = closes[-1]
        if sma5 and sma10 and sma20:
            points += int(sma5 > sma10)
            checks += 1
            points += int(sma10 > sma20)
            checks += 1
            points += int(price > sma20)
            checks += 1
            if sma20 and sma60:
                points += int(sma20 > sma60)
                checks += 1
            m = macd(closes)
            if m["histogram"] is not None:
                points += int(m["histogram"] > 0)
                checks += 1
        score = round(points / checks * 100, 1) if checks else 50.0
        return {"score": score, "detail": {"points": points, "checks": checks}}
