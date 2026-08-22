"""Request parameter contracts.

Response shapes stay compatible with the old API except:
- /api/recommend returns the new factor/sentiment/total_score shape;
- /api/kline source values are extended with "local" (frontend types not yet updated).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenQuery(BaseModel):
    market: str = "all"
    min_score: float = Field(0, ge=0, le=100)
    max_risk: float = Field(100, ge=0, le=100)
    min_trend: float = Field(0, ge=0, le=100)
    min_momentum: float = Field(0, ge=0, le=100)
    min_rsi: float = Field(0, ge=0, le=100)
    max_rsi: float = Field(100, ge=0, le=100)
    sort_by: str = "total_score"
    limit: int = Field(60, ge=1, le=100)


def symbols_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]
