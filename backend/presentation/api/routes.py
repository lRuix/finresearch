"""HTTP routes: validation + service call + compatible response only."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from presentation.api.schemas import ScreenQuery


router = APIRouter()
container = None


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/api/markets")
def markets() -> dict:
    return container.catalog_service.markets()


@router.get("/api/universe")
def universe(market: str = Query("all")) -> dict:
    return container.catalog_service.universe(market)


@router.get("/api/kline")
def kline(market: str, symbol: str, period: str = Query("d", pattern="^(h|d|w)$"),
          limit: int = Query(180, ge=30, le=1000), real: bool = Query(True)) -> dict:
    rows, source = container.analysis_service.kline(
        market, symbol, period, limit, prefer_real=real,
    )
    return {
        "market": market, "symbol": symbol, "period": period,
        "count": len(rows), "source": source,
        "items": rows,
    }


@router.get("/api/analyze")
def analysis(market: str, symbol: str) -> dict:
    return container.analysis_service.analyze(market, symbol)


@router.get("/api/screen")
def run_screen(q: ScreenQuery = Depends()) -> dict:
    result = container.screening_service.screen(
        market=q.market, min_score=q.min_score, max_risk=q.max_risk,
        min_trend=q.min_trend, min_momentum=q.min_momentum,
        min_rsi=q.min_rsi, max_rsi=q.max_rsi, sort_by=q.sort_by, limit=q.limit,
    )
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@router.get("/api/recommendations")
def recommendations(limit: int = Query(10, ge=1, le=20),
                    candidates_per_market: int = Query(20, ge=0, le=100)) -> dict:
    result = container.recommendation_service.recommend(limit, candidates_per_market)
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@router.get("/api/macro")
def macro_payload(live_news: bool = Query(False)) -> dict:
    return container.macro_payload(live_news)


@router.get("/api/search")
def search_instruments_endpoint(q: str = Query("", max_length=64)) -> dict:
    return container.search(q)


@router.get("/api/recommend")
def recommend_symbol(market: str, symbol: str) -> dict:
    return container.analysis_service.recommend(market, symbol)


@router.get("/api/compare")
def compare_symbols(symbols: str = Query("")) -> dict:
    return container.comparison_service.compare(symbols)
