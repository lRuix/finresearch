"""ScreeningService tests with fake dependencies."""
from unittest.mock import MagicMock

from application.services.screening_service import ScreeningService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_screen_returns_expected_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    sync = MagicMock()
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    macro.market_bias.return_value = {"label": "偏多", "score": 60}
    macro.news_items.return_value = []
    service = ScreeningService(
        repo, sync, resolver, macro, MagicMock(), candidates=[
            {"market": "us", "symbol": "AAPL", "name": "Apple",
             "currency": "USD", "sector": "tech", "base_risk": 0.3,
             "liquidity": 0.9},
        ],
    )
    result = service.screen(market="us")
    assert result["total_universe"] == 1
    assert result["items"][0]["symbol"] == "AAPL"
