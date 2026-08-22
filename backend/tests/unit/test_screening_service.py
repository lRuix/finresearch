"""ScreeningService tests with fake dependencies."""
from unittest.mock import MagicMock

from application.services.screening_service import ScreeningService
from application.services.screening_helpers import build_reasons
from domain.models import Instrument, KlineRow
from domain.universe_data import universe_for


def _rows(growth: float = 1.0, count: int = 60):
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i * growth, 1000)
        for i in range(1, count + 1)
    ]


def _candidate(symbol: str, base_risk: float = 0.3):
    return {
        "market": "us", "symbol": symbol, "name": symbol,
        "currency": "USD", "sector": "tech", "base_risk": base_risk,
        "liquidity": 0.9,
    }


def _service(repo=None, sync=None, macro=None, datasource=None, candidates=None):
    return ScreeningService(
        repo or MagicMock(),
        sync or MagicMock(),
        macro or MagicMock(),
        datasource or MagicMock(),
        candidates,
    )


def test_screen_returns_expected_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    macro.market_bias.return_value = {"label": "偏多", "score": 60}
    macro.news_items.return_value = []
    service = _service(repo=repo, macro=macro, candidates=[_candidate("AAPL")])
    result = service.screen(market="us")
    assert result["total_universe"] == 1
    assert result["items"][0]["symbol"] == "AAPL"


def test_screen_filters_by_min_score():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    service = _service(
        repo=repo,
        candidates=[_candidate("AAPL"), _candidate("MSFT")],
    )
    result = service.screen(market="us", min_score=100)
    assert result["items"] == []
    assert result["total_universe"] == 2


def test_screen_sorts_by_total_score_descending():
    repo = MagicMock()
    repo.get_klines.side_effect = [
        _rows(growth=1.0),
        _rows(growth=3.0),
    ]
    service = _service(
        repo=repo,
        candidates=[_candidate("SLOW", base_risk=0.9), _candidate("FAST", base_risk=0.1)],
    )
    result = service.screen(market="us")
    assert result["items"][0]["symbol"] == "FAST"
    assert result["items"][0]["total_score"] >= result["items"][1]["total_score"]


def test_screen_skips_candidate_without_data():
    repo = MagicMock()
    repo.get_klines.return_value = []
    service = _service(repo=repo, candidates=[_candidate("AAPL")])
    result = service.screen(market="us")
    assert result["items"] == []
    assert result["total_universe"] == 1


def test_screen_uses_dynamic_candidates():
    datasource = MagicMock()
    datasource.list_instruments.return_value = [
        Instrument(
            market="us", symbol="AAPL", name="Apple", currency="USD",
            sector="tech", base_risk=0.3, liquidity=0.9,
        ),
    ]
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    service = _service(repo=repo, datasource=datasource)
    result = service.screen(market="us", candidates_per_market=5)
    assert result["total_universe"] == 1
    datasource.list_instruments.assert_called_once_with("us", 5)


def test_screen_uses_builtin_universe():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    service = _service(repo=repo)
    result = service.screen(market="us")
    assert result["total_universe"] == len(universe_for("us"))


def test_build_reasons_limits_news_and_sorts_by_weight():
    macro = MagicMock()
    macro.market_bias.return_value = None
    macro.news_items.return_value = [
        {"tags": ["全球"], "title": "low", "source": "S", "sentiment": -1.0},
        {"tags": ["全球"], "title": "high", "source": "S", "sentiment": 1.0},
        {"tags": ["全球"], "title": "mid", "source": "S", "sentiment": 0.0},
        {"tags": ["全球"], "title": "extra", "source": "S", "sentiment": 0.0},
    ]
    analysis = {
        "trend_score": 0.0, "macd_hist": None, "rsi14": 30.0,
        "change_20d": 0.0, "momentum_score": 50.0,
    }
    reasons = build_reasons(
        {"market": "us", "symbol": "AAPL", "name": "Apple"},
        analysis,
        macro,
    )
    assert [reason["title"] for reason in reasons] == ["high", "mid", "low"]


def test_screen_treats_zero_base_risk_as_zero():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    service = _service(repo=repo, candidates=[_candidate("ZERO", base_risk=0.0)])
    result = service.screen(market="us", max_risk=50)
    assert result["total_universe"] == 1
    assert result["items"] == []


def test_screen_missing_base_risk_uses_default():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    candidate = _candidate("MISSING")
    candidate.pop("base_risk")
    service = _service(repo=repo, candidates=[candidate])
    result = service.screen(market="us", max_risk=50)
    assert result["total_universe"] == 1
    assert result["items"][0]["symbol"] == "MISSING"
