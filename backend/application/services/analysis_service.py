"""Single-instrument analysis orchestration."""
from __future__ import annotations

from application.ports import MacroNewsProvider, MarketDataRepository
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.indicators import analyze


class AnalysisService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 macro_news: MacroNewsProvider):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._macro = macro_news

    def analyze(self, market: str, symbol: str) -> dict:
        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            self._sync.sync(market, symbol, "d")
            rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        enriched = dict(meta)
        enriched["macro_score"] = self._macro.macro_score(market)
        kline_dicts = [
            {
                "time": row.time, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close, "volume": row.volume,
            }
            for row in rows
        ]
        result = analyze(kline_dicts, enriched)
        return {
            "meta": meta,
            "macro_bias": self._macro.market_bias(market),
            "analysis": result,
            "kline_count": len(rows),
        }

    def kline(self, market: str, symbol: str, period: str,
              limit: int, prefer_real: bool = True) -> tuple[list[dict], str]:
        rows = self._repository.get_klines(market, symbol, period)
        if rows:
            return [row.__dict__ for row in rows[-limit:]], "local"
        _, source = self._sync.sync(market, symbol, period)
        rows = self._repository.get_klines(market, symbol, period)
        return [row.__dict__ for row in rows[-limit:]], source if rows else "mock"

    def recommend(self, market: str, symbol: str) -> dict:
        """Compatibility shape for the legacy /api/recommend endpoint."""
        from domain.algorithms.config import build_engine
        from domain.algorithms.context import AnalysisContext

        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            self._sync.sync(market, symbol, "d")
            rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        currency = meta.get("currency") or self._resolver.currency_for(market)
        ctx = AnalysisContext(
            symbol=symbol,
            market=market,
            currency=currency,
            klines=[
                {
                    "time": row.time, "open": row.open, "high": row.high,
                    "low": row.low, "close": row.close, "volume": row.volume,
                }
                for row in rows
            ],
            macro_bias=self._macro.macro_score(market),
            news_sentiment=0.0,
            fx_rate=None,
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
