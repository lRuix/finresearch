"""动量因子：RSI 位置 + 20 日涨跌修正。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import rsi


def _clamp(v: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, v))


class MomentumFactor(Factor):
    name = "momentum"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        rsi14 = rsi(closes, 14)
        if rsi14 is None:
            base = 50.0
        elif 48 <= rsi14 <= 62:
            base = 82.0
        elif 42 <= rsi14 <= 70:
            base = 68.0
        elif rsi14 < 30 or rsi14 > 80:
            base = 32.0
        else:
            base = 50.0
        change_20d = 0.0
        if len(closes) >= 21 and closes[-21]:
            change_20d = (closes[-1] / closes[-21] - 1) * 100
        if change_20d > 5:
            base = _clamp(base + 12)
        elif change_20d < -5:
            base = _clamp(base - 10)
        return {"score": round(base, 1), "detail": {"rsi14": rsi14, "change_20d": round(change_20d, 2)}}
