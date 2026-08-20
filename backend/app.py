"""FastAPI entry point for the finance research terminal."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from core import comparison, macro, screener, search
from core.algorithms.config import build_engine
from core.algorithms.context import AnalysisContext
from core.indicators import analyze
from core.providers import get_kline, get_kline_with_source
from core.search import search as search_instruments
from core.universe import MARKETS, UNIVERSE, find_symbol, universe_for
from core.valuation import currency as currency_util


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


def _market_sentiment(market: str) -> float:
    """取该市场相关新闻的平均 sentiment（-1..1），无则 0.0。"""
    tags = {
        "a-share": {"A股", "政策", "信用"},
        "fund": {"A股", "政策", "ETF"},
        "us": {"美股", "利率", "美元", "全球"},
        "kr": {"韩股", "半导体", "汇率", "全球"},
        "hk": {"港股", "南向资金", "政策"},
        "fx": {"汇率", "美元", "利率", "全球"},
        "crypto": {"数字货币", "ETF", "全球"},
    }
    wanted = tags.get(market, {"全球"})
    scores = [n["sentiment"] for n in macro.NEWS_ITEMS if set(n["tags"]) & wanted]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


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


@app.get("/api/search")
def search_instruments_endpoint(q: str = Query("", max_length=64)) -> dict:
    return search_instruments(q)


@app.get("/api/recommend")
def recommend_symbol(market: str, symbol: str) -> dict:
    rows = get_kline(market, symbol, "d", 180, prefer_real=True)
    if not rows:
        return {"error": "no kline data", "market": market, "symbol": symbol}
    meta = search.resolve_meta(market, symbol) or {}
    currency = search.currency_for(market)
    # 新闻情绪：取该市场新闻平均 sentiment（macro.NEWS_ITEMS 的 sentiment 字段）
    news_sentiment = _market_sentiment(market)
    ctx = AnalysisContext(
        symbol=symbol,
        market=market,
        currency=currency,
        klines=rows,
        macro_bias=macro.macro_score_for(market),
        news_sentiment=news_sentiment,
        fx_rate=currency_util.reference_fx_rate(currency),
        horizon="short",
    )
    engine = build_engine()
    factor_scores = {}
    factor_details = {}
    for factor in engine.factors:
        result = factor.score(ctx)
        factor_scores[factor.name] = result["score"]
        factor_details[factor.name] = result.get("detail", {})
    sentiment = engine.sentiment.analyze(ctx)
    combined = engine.combine(factor_scores, sentiment)
    return {
        "meta": meta,
        "market": market,
        "symbol": symbol,
        "currency": currency,
        "factor_scores": factor_scores,
        "factor_details": factor_details,
        "sentiment": sentiment,
        "total_score": combined["total_score"],
        "detail": combined.get("detail", {}),
    }


@app.get("/api/compare")
def compare_symbols(symbols: str = Query("")) -> dict:
    tokens = [t.strip() for t in symbols.split(",") if t.strip()]
    assets = []
    for token in tokens:
        mkt = search.detect_market(token)
        if mkt is None:
            continue
        sym = search.normalize_symbol(mkt, token)
        rows = get_kline(mkt, sym, "d", 180, prefer_real=True)
        if not rows:
            continue
        currency = search.currency_for(mkt)
        fx_rate = currency_util.reference_fx_rate(currency)
        local_closes = [r["close"] for r in rows]
        assets.append({
            "symbol": sym,
            "name": token,
            "market": mkt,
            "currency": currency,
            "rmb_closes": currency_util.to_rmb_closes(local_closes, fx_rate),
        })
    return {"items": comparison.compare_assets(assets), "total": len(assets)}
