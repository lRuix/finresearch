"""风险调整后收益指标。"""
from __future__ import annotations

import math


def max_drawdown(closes: list[float]) -> float:
    """最大回撤，返回正小数（0.25 表示 -25%）。"""
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 6)


def annualized_return(closes: list[float], periods_per_year: int = 252) -> float:
    if len(closes) < 2 or closes[0] <= 0:
        return 0.0
    total = closes[-1] / closes[0] - 1
    years = (len(closes) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return (1 + total) ** (1 / years) - 1


def calmar_ratio(closes: list[float], periods_per_year: int = 252) -> float | None:
    md = max_drawdown(closes)
    if md <= 0:
        return None
    return annualized_return(closes, periods_per_year) / md


def sharpe_ratio(closes: list[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    if len(closes) < 2:
        return 0.0
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    if len(returns) < 2:
        return 0.0
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std <= 0:
        return 0.0
    return (mean * periods_per_year - risk_free) / (std * math.sqrt(periods_per_year))
