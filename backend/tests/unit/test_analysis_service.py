"""AnalysisService tests."""
from unittest.mock import MagicMock

from application.services.analysis_service import AnalysisService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_analyze_returns_compatible_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    sync = MagicMock()
    sync.sync.return_value = []
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
    service = AnalysisService(repo, sync, resolver, macro)
    result = service.analyze("us", "AAPL")
    assert result["meta"]["symbol"] == "AAPL"
    assert result["kline_count"] == 60
    assert "analysis" in result
