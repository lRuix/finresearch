"""Search service: arbitrary symbol search via resolver and universe data."""
from __future__ import annotations

import re

from application.ports import MarketDataSource
from application.services.symbol_resolver import SymbolResolver
from domain.universe_data import UNIVERSE


class SearchService:
    def __init__(self, datasource: MarketDataSource,
                 symbol_resolver: SymbolResolver | None = None):
        self._resolver = symbol_resolver or SymbolResolver(datasource)

    def search(self, query: str, limit: int = 10) -> dict:
        q = (query or "").strip()
        items: list[dict] = []
        q_upper = q.upper()
        for item in UNIVERSE:
            if q_upper and (
                item["symbol"].upper().startswith(q_upper)
                or q_upper in item["name"].upper()
            ):
                items.append({**item, "matched": "universe"})
            if len(items) >= limit:
                break
        if q and not re.search(r"[\u4e00-\u9fff]", q):
            market = self._resolver.detect_market(q)
            if market is not None:
                symbol = self._resolver.normalize_symbol(market, q)
                try:
                    meta = self._resolver.resolve_meta(market, symbol)
                    if meta is not None and not any(
                        i["symbol"] == meta["symbol"] for i in items
                    ):
                        items.append({**meta, "matched": "auto"})
                except Exception:
                    pass
        return {"query": q, "items": items[:limit], "total": len(items)}
