"""Cross-market recommendation orchestration with daily evaluation cache."""
from __future__ import annotations

from datetime import date

from application.ports import MarketDataRepository
from application.services.screening_service import ScreeningService


QUOTAS = {
    "a-share": 2, "us": 2, "kr": 1, "hk": 1, "fund": 1,
    "fx": 1, "crypto": 2,
}


class RecommendationService:
    def __init__(self, repository: MarketDataRepository,
                 screening_service: ScreeningService):
        self._repository = repository
        self._screening = screening_service

    def recommend(self, limit: int = 10, candidates_per_market: int = 0) -> dict:
        today = date.today().isoformat()
        cache_key = f"recommend:{limit}:{candidates_per_market}"
        cached = self._repository.get_evaluation(today, "all", cache_key)
        if cached is not None:
            return cached
        results = self._screening.screen(
            market="all",
            candidates_per_market=candidates_per_market,
            limit=100,
        )
        picked = self._pick(results["items"], limit)
        payload = {
            "items": picked,
            "count": len(picked),
            "total_universe": results["total_universe"],
        }
        self._repository.save_evaluation(
            today, "all", cache_key,
            len(picked), payload,
        )
        return payload

    def _pick(self, results: list[dict], limit: int) -> list[dict]:
        picked: list[dict] = []
        picked_keys: set[tuple[str, str]] = set()
        for market_id, quota in QUOTAS.items():
            group = [item for item in results if item["market"] == market_id]
            group.sort(key=lambda item: item["total_score"], reverse=True)
            for item in group[:quota]:
                picked.append(item)
                picked_keys.add((item["market"], item["symbol"]))
        remaining = [item for item in results
                     if (item["market"], item["symbol"]) not in picked_keys]
        remaining.sort(key=lambda item: item["total_score"], reverse=True)
        for item in remaining:
            if len(picked) >= limit:
                break
            picked.append(item)
            picked_keys.add((item["market"], item["symbol"]))
        market_presence = {item["market"] for item in picked}
        for required in ("fx", "crypto"):
            if required in market_presence:
                continue
            fallback = next((item for item in results if item["market"] == required), None)
            if fallback is not None:
                lowest = min(picked, key=lambda item: item["total_score"])
                picked.remove(lowest)
                picked.append(fallback)
                market_presence.add(required)
        picked.sort(key=lambda item: item["total_score"], reverse=True)
        return picked[:limit]
