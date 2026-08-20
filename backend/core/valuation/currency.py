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


def to_rmb_closes(closes: list[float], fx_rate: float) -> list[float]:
    """本币收盘价序列折算为 RMB 口径：rmb_price = local_price × fx_rate。

    closes: 本币收盘价序列
    fx_rate: 本币 → RMB 汇率（1 本币 = fx_rate RMB），CNY 时传 1.0
    """
    return [c * fx_rate for c in closes]


#: 本币 → RMB 参考汇率（1 本币 = 多少 RMB）。CNY=1.0；其余为静态参考值，
#: 生产环境应由 providers 的 frankfurter 实时填充（后续优化）。
_REFERENCE_FX_RATE = {
    "CNY": 1.0,
    "USD": 7.18,
    "HKD": 0.92,
    "KRW": 0.0053,
    "USDT": 7.18,
    "MULTI": 1.0,
}


def reference_fx_rate(currency: str) -> float:
    """本币 → RMB 参考汇率，未知币种回落 1.0。"""
    return _REFERENCE_FX_RATE.get(currency, 1.0)
