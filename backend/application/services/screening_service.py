"""Screening orchestration: candidates -> concurrent scoring -> filters."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from application.ports import MacroNewsProvider, MarketDataSource, MarketDataRepository
from application.services.screening_helpers import asset_type, build_reasons, market_name
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.indicators import analyze
from domain.universe_data import MARKETS, universe_for


class ScreeningService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 macro_news: MacroNewsProvider,
                 datasource: MarketDataSource,
                 candidates: list[dict] | None = None):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._macro = macro_news
        self._datasource = datasource
        self._candidates = candidates

    def _candidate_pool(self, market: str, candidates_per_market: int) -> list[dict]:
        if self._candidates is not None:
            return self._candidates
        if candidates_per_market > 0:
            if market == "all":
                return [
                    item
                    for market_info in MARKETS
                    for item in self._list_candidates(market_info["id"], candidates_per_market)
                ]
            return self._list_candidates(market, candidates_per_market)
        return universe_for(market)

    def _list_candidates(self, market: str, top_n: int) -> list[dict]:
        instruments = self._datasource.list_instruments(market, top_n)
        return [item.__dict__ for item in instruments]

    def _build_candidate(self, item: dict, min_score: float, max_risk: float,
                         min_trend: float, min_momentum: float,
                         min_rsi: float, max_rsi: float) -> dict | None:
        rows = self._repository.get_klines(item["market"], item["symbol"], "d")
        if not rows or len(rows) < 30:
            self._sync.sync(item["market"], item["symbol"], "d")
            rows = self._repository.get_klines(item["market"], item["symbol"], "d")
        if not rows:
            return None
        kline_dicts = [
            {
                "time": row.time, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close, "volume": row.volume,
            }
            for row in rows
        ]
        enriched = dict(item)
        enriched["macro_score"] = self._macro.macro_score(item["market"])
        analysis = analyze(kline_dicts, enriched)
        if "error" in analysis:
            return None
        rsi = analysis["rsi14"] or 50
        risk = (1 - item["base_risk"]) * 100
        if (analysis["total_score"] < min_score or risk > max_risk
                or analysis["trend_score"] < min_trend
                or analysis["momentum_score"] < min_momentum
                or rsi < min_rsi or rsi > max_rsi):
            return None
        return {
            "symbol": item["symbol"],
            "name": item["name"],
            "market": item["market"],
            "market_name": market_name(item["market"]),
            "asset_type": asset_type(item),
            "sector": item["sector"],
            "currency": item["currency"],
            "price": analysis["price"],
            "change_1d": analysis["change_1d"],
            "change_20d": analysis["change_20d"],
            "rsi14": analysis["rsi14"],
            "trend_score": analysis["trend_score"],
            "momentum_score": analysis["momentum_score"],
            "volatility20": analysis["volatility20"],
            "macro_score": analysis["macro_score"],
            "total_score": analysis["total_score"],
            "signals": analysis["signals"][:3],
            "reasons": build_reasons(item, analysis, self._macro),
        }

    def screen(self, market: str = "all", min_score: float = 0,
               max_risk: float = 100, min_trend: float = 0,
               min_momentum: float = 0, min_rsi: float = 0,
               max_rsi: float = 100, sort_by: str = "total_score",
               limit: int = 60, candidates_per_market: int = 0) -> dict:
        items = self._candidate_pool(market, candidates_per_market)

        def build(item):
            return self._build_candidate(
                item, min_score, max_risk, min_trend, min_momentum,
                min_rsi, max_rsi,
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = [r for r in executor.map(build, items) if r is not None]
        allowed_sort = {
            "total_score": "total_score",
            "change_20d": "change_20d",
            "rsi14": "rsi14",
            "trend_score": "trend_score",
        }
        key = allowed_sort.get(sort_by, "total_score")
        results.sort(key=lambda item: item[key], reverse=True)
        return {
            "items": results[:limit],
            "count": len(results),
            "total_universe": len(items),
        }
