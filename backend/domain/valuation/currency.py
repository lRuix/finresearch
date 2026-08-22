"""Unified RMB valuation, pure functions only.

The real-time fx rate is injected by application services via FxRateProvider;
this module never imports providers or makes network requests.
"""
from __future__ import annotations

from types import MappingProxyType


def to_rmb_returns(returns: list[float], fx_change: float) -> list[float]:
    factor = 1 + fx_change
    return [(1 + r) * factor - 1 for r in returns]


def to_rmb_closes(closes: list[float], fx_rate: float) -> list[float]:
    return [c * fx_rate for c in closes]


STATIC_FX_RATES = MappingProxyType({
    "CNY": 1.0,
    "USD": 7.18,
    "HKD": 0.92,
    "KRW": 0.0053,
    "USDT": 7.18,
    "MULTI": 1.0,
})


def static_reference_fx_rate(currency: str) -> float:
    return STATIC_FX_RATES.get(currency, 1.0)
