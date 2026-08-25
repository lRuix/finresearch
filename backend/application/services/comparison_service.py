"""Cross-asset comparison orchestration with injected fx rates."""
from __future__ import annotations

from application.ports import FxRateProvider, MarketDataRepository
from application.services.symbol_resolver import SymbolResolver
from domain.valuation import currency as currency_util
from domain.valuation.constraints import quota_note, requires_quota
from domain.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


class ComparisonService:
    def __init__(self, repository: MarketDataRepository,
                 symbol_resolver: SymbolResolver,
                 fx_provider: FxRateProvider):
        self._repository = repository
        self._resolver = symbol_resolver
        self._fx = fx_provider

    def compare(self, symbols: str) -> dict:
        tokens = [token.strip() for token in symbols.split(",") if token.strip()]
        assets = []
        for token in tokens:
            market = self._resolver.detect_market(token)
            if market is None:
                continue
            symbol = self._resolver.normalize_symbol(market, token)
            rows = self._repository.get_klines(market, symbol, "d")
            if not rows:
                continue
            currency = self._resolver.currency_for(market)
            fx_rate = self._fx.reference_fx_rate(currency)
            closes = [row.close for row in rows]
            assets.append({
                "symbol": symbol,
                "name": token,
                "market": market,
                "currency": currency,
                "rmb_closes": currency_util.to_rmb_closes(closes, fx_rate),
            })
        return {"items": self._compare_assets(assets), "total": len(assets)}

    def _compare_assets(self, assets: list[dict]) -> list[dict]:
        results = []
        for asset in assets:
            closes = asset["rmb_closes"]
            calmar = calmar_ratio(closes)
            quota = requires_quota(asset["market"])
            results.append({
                "symbol": asset["symbol"],
                "name": asset["name"],
                "market": asset["market"],
                "currency": asset["currency"],
                "rmb_annual_return": round(annualized_return(closes), 4),
                "max_drawdown": round(max_drawdown(closes), 4),
                "calmar_ratio": round(calmar, 4) if calmar is not None else None,
                "sharpe_ratio": round(sharpe_ratio(closes), 4),
                "requires_quota": quota,
                "quota_note": quota_note(0.0) if quota else "",
            })
        results.sort(key=lambda item: (item["calmar_ratio"] is None,
                                       -(item["calmar_ratio"] or 0)))
        return results
