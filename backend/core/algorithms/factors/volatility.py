"""低波动因子：年化波动率 vs 市场目标分档。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import annualized_volatility

_VOL_TARGET = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}


class VolatilityFactor(Factor):
    name = "volatility"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        vol = annualized_volatility(closes, 20)
        target = _VOL_TARGET.get(ctx.market, 0.28)
        if vol is None:
            s = 50.0
        elif vol <= target * 0.8:
            s = 72.0
        elif vol <= target * 1.15:
            s = 86.0
        elif vol <= target * 1.6:
            s = 58.0
        else:
            s = 34.0
        return {"score": s, "detail": {"vol20": vol, "target": target}}
