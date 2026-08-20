"""宏观因子：直接使用市场偏置分。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor


class MacroFactor(Factor):
    name = "macro"

    def score(self, ctx: AnalysisContext) -> dict:
        return {"score": round(float(ctx.macro_bias), 1), "detail": {"bias": ctx.macro_bias}}
