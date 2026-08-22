"""ComparisonService tests."""
from unittest.mock import MagicMock

from application.services.comparison_service import ComparisonService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_compare_sorts_assets_by_calmar():
    repo = MagicMock()
    repo.get_klines.side_effect = lambda market, symbol, period, **kw: _rows()
    sync = MagicMock()
    resolver = MagicMock()
    resolver.detect_market.side_effect = lambda token: {
        "AAPL": "us", "600519": "a-share",
    }.get(token)
    resolver.normalize_symbol.side_effect = lambda market, token: token
    resolver.currency_for.side_effect = lambda market: "USD"
    fx = MagicMock()
    fx.reference_fx_rate.return_value = 7.18
    service = ComparisonService(repo, sync, resolver, fx)
    result = service.compare("AAPL,600519")
    assert result["total"] == 2
    assert all("calmar_ratio" in item for item in result["items"])
