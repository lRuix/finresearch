"""Domain value objects shared by application and algorithm layers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    """Market instrument DTO.

    base_risk / liquidity are optional DTO fields without range validation;
    callers are responsible for supplying semantically valid values.
    """

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

    def __post_init__(self) -> None:
        if self.low < 0 or self.high < 0 or self.open < 0 or self.close < 0:
            raise ValueError("Kline prices must be non-negative")
        if self.high < self.low:
            raise ValueError("Kline high must be >= low")
        if self.volume < 0:
            raise ValueError("Kline volume must be non-negative")
