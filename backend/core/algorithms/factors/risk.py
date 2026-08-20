"""风险因子：波动率反推风险系数 → (1-risk)*100。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import annualized_volatility

_VOL_TARGET = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}


class RiskFactor(Factor):
    name = "risk"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        vol = annualized_volatility(closes, 20)
        target = _VOL_TARGET.get(ctx.market, 0.28)
        ratio = (vol / target) if (vol and target) else 1.0
        if ratio <= 0.6:
            risk = 0.35
        elif ratio <= 0.9:
            risk = 0.45
        elif ratio <= 1.2:
            risk = 0.58
        elif ratio <= 1.7:
            risk = 0.72
        elif ratio <= 2.4:
            risk = 0.84
        else:
            risk = 0.93
        return {"score": round((1 - risk) * 100, 1), "detail": {"risk_coef": risk, "vol20": vol}}
