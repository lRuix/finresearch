"""AnalysisService tests."""
from unittest.mock import MagicMock

from application.services.analysis_service import AnalysisService
from domain.models import KlineRow


def _rows(count: int = 60):
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, count + 1)
    ]


def _service(repo=None, sync=None, resolver=None, macro=None, fx=None):
    return AnalysisService(
        repo or MagicMock(),
        sync or MagicMock(),
        resolver or MagicMock(),
        macro or MagicMock(),
        fx,
    )


def test_analyze_returns_compatible_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
    service = _service(repo=repo, resolver=resolver, macro=macro)
    result = service.analyze("us", "AAPL")
    assert result["meta"]["symbol"] == "AAPL"
    assert result["kline_count"] == 60
    assert "analysis" in result


def test_analyze_symbol_not_found():
    resolver = MagicMock()
    resolver.resolve_meta.return_value = None
    result = _service(resolver=resolver).analyze("us", "ZZZZ")
    assert result == {"error": "symbol not found"}


def test_analyze_no_data_after_sync():
    repo = MagicMock()
    repo.get_klines.return_value = []
    service = _service(repo=repo)
    result = service.analyze("us", "ZZZZ")
    assert result["error"] == "no kline data"


def test_kline_sources_local_and_live():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    items, source = _service(repo=repo).kline("us", "AAPL", "d", 30)
    assert source == "local"
    assert len(items) == 30
    assert "close" in items[0]

    repo2 = MagicMock()
    repo2.get_klines.side_effect = [[], _rows()]
    sync = MagicMock()
    sync.sync.return_value = (_rows(), "live")
    _, source2 = _service(repo=repo2, sync=sync).kline("us", "AAPL", "d", 30)
    assert source2 == "live"


def test_kline_forwards_prefer_real():
    repo = MagicMock()
    repo.get_klines.side_effect = [[], _rows()]
    sync = MagicMock()
    sync.sync.return_value = (_rows(), "mock")
    service = _service(repo=repo, sync=sync)
    _, source = service.kline("us", "AAPL", "d", 30, prefer_real=False)
    assert source == "mock"
    assert sync.sync.call_args.kwargs["prefer_real"] is False


def test_recommend_uses_market_news_sentiment_and_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    macro.news_items.return_value = [{"sentiment": 0.2}, {"sentiment": 0.4}]
    service = _service(repo=repo, resolver=resolver, macro=macro)
    result = service.recommend("us", "AAPL")
    assert set(result) >= {
        "factor_scores", "factor_details", "sentiment", "total_score", "detail",
    }
    assert 0 <= result["total_score"] <= 100
    macro.news_items.assert_called_once_with("us")
    assert result["sentiment"]["polarity"] == 0.3


def test_ensure_klines_triggers_sync_when_short():
    repo = MagicMock()
    repo.get_klines.side_effect = [_rows(29), _rows(60)]
    sync = MagicMock()
    sync.sync.return_value = (_rows(), "live")
    service = _service(repo=repo, sync=sync)
    rows = service._ensure_klines("us", "AAPL", "d")
    assert len(rows) == 60
    assert sync.sync.called
