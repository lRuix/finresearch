"""Domain value objects shared by application and algorithm layers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    market: str
    symbol: str
    name: str
    currency: str
    sector: str | None = None
    base_risk: float | None = None
    liquidity: float | None = None


@dataclass(frozen=True)
class KlineRow:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
