"""Single-instrument analysis orchestration."""
from __future__ import annotations

from application.ports import (
    FxRateProvider,
    MacroNewsProvider,
    MarketDataRepository,
)
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.indicators import analyze


def _kline_dict(row) -> dict:
    return {
        "time": row.time, "open": row.open, "high": row.high,
        "low": row.low, "close": row.close, "volume": row.volume,
    }


class AnalysisService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 macro_news: MacroNewsProvider,
                 fx_provider: FxRateProvider | None = None):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._macro = macro_news
        self._fx = fx_provider

    def _ensure_klines(self, market: str, symbol: str, period: str,
                       prefer_real: bool = True) -> list:
        rows = self._repository.get_klines(market, symbol, period)
        if not rows or len(rows) < 30:
            self._sync.sync(market, symbol, period, prefer_real=prefer_real)
            rows = self._repository.get_klines(market, symbol, period)
        return rows

    def analyze(self, market: str, symbol: str) -> dict:
        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._ensure_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        enriched = dict(meta)
        enriched["macro_score"] = self._macro.macro_score(market)
        kline_dicts = [_kline_dict(row) for row in rows]
        result = analyze(kline_dicts, enriched)
        return {
            "meta": meta,
            "macro_bias": self._macro.market_bias(market),
            "analysis": result,
            "kline_count": len(rows),
        }

    def kline(self, market: str, symbol: str, period: str,
              limit: int, prefer_real: bool = True) -> tuple[list[dict], str]:
        """Return (items, source). 'local' means served from the local repository."""
        rows = self._repository.get_klines(market, symbol, period)
        if rows and len(rows) >= limit:
            return [_kline_dict(row) for row in rows[-limit:]], "local"

        if rows:
            # 本地历史不足 limit 时强制全量同步补齐，避免宽屏请求更多数据仍只返回旧缓存。
            self._sync.sync(
                market, symbol, period, prefer_real=prefer_real, force_full=True,
            )
            rows = self._repository.get_klines(market, symbol, period)
            if rows:
                return [_kline_dict(row) for row in rows[-limit:]], "local"
            return [], "mock"

        _, source = self._sync.sync(market, symbol, period, prefer_real=prefer_real)
        rows = self._repository.get_klines(market, symbol, period)
        return [_kline_dict(row) for row in rows[-limit:]], source if rows else "mock"

    def _market_sentiment(self, market: str) -> float:
        scores = [item.get("sentiment") for item in self._macro.news_items(market)]
        scores = [float(s) for s in scores if s is not None]
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)

    def recommend(self, market: str, symbol: str) -> dict:
        """Compatibility shape for the legacy /api/recommend endpoint."""
        from domain.algorithms.config import build_engine
        from domain.algorithms.context import AnalysisContext

        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._ensure_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        currency = meta.get("currency") or self._resolver.currency_for(market)
        fx_rate = self._fx.reference_fx_rate(currency) if self._fx else None
        ctx = AnalysisContext(
            symbol=symbol,
            market=market,
            currency=currency,
            klines=[_kline_dict(row) for row in rows],
            macro_bias=self._macro.macro_score(market),
            news_sentiment=self._market_sentiment(market),
            fx_rate=fx_rate,
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
