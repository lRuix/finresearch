"""RecommendationService tests."""
from unittest.mock import MagicMock

from application.services.recommendation_service import RecommendationService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_recommendation_uses_daily_evaluation_cache():
    repo = MagicMock()
    repo.get_evaluation.return_value = {
        "items": [{"symbol": "AAPL"}], "count": 1, "total_universe": 1,
    }
    service = RecommendationService(repo, MagicMock())
    result = service.recommend()
    assert result["items"][0]["symbol"] == "AAPL"
