"""FastAPI entry point for the finance research terminal."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from core import macro, screener
from core.indicators import analyze
from core.providers import get_kline, get_kline_with_source
from core.universe import MARKETS, UNIVERSE, find_symbol, universe_for


app = FastAPI(
    title="Global Finance Research Terminal",
    description="全球投资标的筛选与 K 线研究 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/markets")
def markets() -> dict:
    return {"items": MARKETS, "total": len(MARKETS)}


@app.get("/api/universe")
def universe(market: str = Query("all")) -> dict:
    items = universe_for(market)
    return {"items": items, "total": len(items)}


@app.get("/api/kline")
def kline(
    market: str,
    symbol: str,
    period: str = Query("d", pattern="^(h|d|w)$"),
    limit: int = Query(180, ge=30, le=1000),
    real: bool = Query(True),
) -> dict:
    rows, source = get_kline_with_source(market, symbol, period, limit, prefer_real=real)
    return {
        "market": market,
        "symbol": symbol,
        "period": period,
        "count": len(rows),
        "source": source,
        "items": rows,
    }


@app.get("/api/analyze")
def analysis(market: str, symbol: str) -> dict:
    meta = find_symbol(market, symbol)
    if meta is None:
        return {"error": "symbol not found"}
    rows = get_kline(market, symbol, "d", 180, prefer_real=True)
    enriched = dict(meta)
    enriched["macro_score"] = macro.macro_score_for(market)
    result = analyze(rows, enriched)
    return {
        "meta": meta,
        "macro_bias": macro.MARKET_BIAS.get(market),
        "analysis": result,
        "kline_count": len(rows),
    }


@app.get("/api/screen")
def run_screen(
    market: str = Query("all"),
    min_score: float = Query(0, ge=0, le=100),
    max_risk: float = Query(100, ge=0, le=100),
    min_trend: float = Query(0, ge=0, le=100),
    min_momentum: float = Query(0, ge=0, le=100),
    min_rsi: float = Query(0, ge=0, le=100),
    max_rsi: float = Query(100, ge=0, le=100),
    sort_by: str = Query("total_score"),
    limit: int = Query(60, ge=1, le=100),
) -> dict:
    result = screener.screen(
        market=market,
        min_score=min_score,
        max_risk=max_risk,
        min_trend=min_trend,
        min_momentum=min_momentum,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        sort_by=sort_by,
        limit=limit,
    )
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@app.get("/api/recommendations")
def recommendations(limit: int = Query(10, ge=1, le=20)) -> dict:
    result = screener.recommend(limit=limit)
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@app.get("/api/macro")
def macro_payload(live_news: bool = Query(False)) -> dict:
    payload = macro.macro_payload(live_news=live_news)
    payload["universe_size"] = len(UNIVERSE)
    return payload
