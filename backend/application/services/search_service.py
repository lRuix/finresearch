"""Search service: arbitrary symbol search (wraps legacy core.search)."""
from __future__ import annotations

from core.search import search as _search


class SearchService:
    def search(self, query: str, limit: int = 10) -> dict:
        return _search(query, limit)
