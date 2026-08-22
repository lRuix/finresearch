"""Market catalog service: markets and universe listing."""
from __future__ import annotations

from domain.universe_data import MARKETS, universe_for


class CatalogService:
    def markets(self) -> dict:
        return {"items": MARKETS, "total": len(MARKETS)}

    def universe(self, market: str) -> dict:
        items = universe_for(market)
        return {"items": items, "total": len(items)}
