"""统一 RMB 计价。"""
from __future__ import annotations


def to_rmb_returns(returns: list[float], fx_change: float) -> list[float]:
    """本币收益率序列折算为 RMB 口径：收益(RMB) = (1+收益(本币)) × (1+汇率变动率) - 1。

    returns: 本币各期收益率（小数，如 0.10 表示 +10%）
    fx_change: 期间汇率变动率（本币相对 RMB，+ 表示本币升值）
    """
    factor = 1 + fx_change
    return [(1 + r) * factor - 1 for r in returns]


def market_fx_rate(market: str, currency: str) -> float | None:
    """本币 → RMB 汇率。CNY 计价直接返回 1.0；其余返回 None（需外部填充）。"""
    if currency == "CNY":
        return 1.0
    return None
