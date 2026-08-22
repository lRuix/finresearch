"""RecommendationService tests."""
from datetime import date
from unittest.mock import MagicMock

from application.services.recommendation_service import RecommendationService


def _item(market: str, symbol: str, score: float) -> dict:
    return {"market": market, "symbol": symbol, "total_score": score}


def _results():
    return [
        _item("a-share", "A1", 100), _item("a-share", "A2", 99),
        _item("us", "U1", 98), _item("us", "U2", 97),
        _item("kr", "K1", 96), _item("hk", "H1", 95),
        _item("fund", "F1", 94), _item("fx", "FX", 10),
        _item("crypto", "C1", 9), _item("crypto", "C2", 8),
    ]


def test_recommendation_uses_daily_evaluation_cache():
    repo = MagicMock()
    repo.get_evaluation.return_value = {
        "items": [{"symbol": "AAPL"}], "count": 1, "total_universe": 1,
    }
    service = RecommendationService(repo, MagicMock())
    result = service.recommend()
    assert result["items"][0]["symbol"] == "AAPL"


def test_recommendation_miss_saves_with_today_key():
    repo = MagicMock()
    repo.get_evaluation.return_value = None
    screening = MagicMock()
    screening.screen.return_value = {
        "items": _results(), "count": 10, "total_universe": 10,
    }
    service = RecommendationService(repo, screening)
    result = service.recommend(limit=8, candidates_per_market=2)
    assert result["count"] == 8
    screening.screen.assert_called_once_with(
        market="all", candidates_per_market=2, limit=None,
    )
    repo.save_evaluation.assert_called_once()
    args = repo.save_evaluation.call_args.args
    assert args[0] == date.today().isoformat()
    assert args[1] == "all"
    assert args[2] == "recommend:8:2"


def test_pick_keeps_fx_and_crypto_when_limit_small():
    service = RecommendationService(MagicMock(), MagicMock())
    picked = service._pick(_results(), 5)
    markets = {item["market"] for item in picked}
    assert {"fx", "crypto"} <= markets


def test_pick_empty_results():
    service = RecommendationService(MagicMock(), MagicMock())
    assert service._pick([], 10) == []


def test_recommendation_empty_results_saves_empty_payload():
    repo = MagicMock()
    repo.get_evaluation.return_value = None
    screening = MagicMock()
    screening.screen.return_value = {"items": [], "count": 0, "total_universe": 0}
    service = RecommendationService(repo, screening)
    result = service.recommend()
    assert result == {"items": [], "count": 0, "total_universe": 0}
    assert repo.save_evaluation.called
