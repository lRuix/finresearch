"""ComparisonService tests."""
from unittest.mock import MagicMock, call

from application.services.comparison_service import ComparisonService
from domain.models import KlineRow


def _rows(count: int = 60):
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, count + 1)
    ]


def _rising():
    return [100 + i for i in range(60)]


def _falling():
    return [100 - i * 0.5 for i in range(60)]


def _recovering():
    values = [100.0]
    for i in range(1, 60):
        if i % 5 == 0:
            values.append(values[-1] - 10)
        else:
            values.append(values[-1] + 3)
    return values


def test_compare_sorts_by_calmar_descending_none_last():
    service = ComparisonService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    results = service._compare_assets([
        {"symbol": "RISE", "name": "R", "market": "us", "currency": "USD",
         "rmb_closes": _rising()},
        {"symbol": "FALL", "name": "F", "market": "hk", "currency": "HKD",
         "rmb_closes": _falling()},
        {"symbol": "RECOVER", "name": "V", "market": "a-share", "currency": "CNY",
         "rmb_closes": _recovering()},
    ])
    symbols = [item["symbol"] for item in results]
    assert symbols[0] == "RECOVER"
    assert symbols.index("FALL") < symbols.index("RISE")
    assert results[-1]["calmar_ratio"] is None


def test_compare_injects_fx_by_currency():
    repo = MagicMock()
    repo.get_klines.side_effect = lambda market, symbol, period, **kw: _rows()
    resolver = MagicMock()
    resolver.detect_market.side_effect = {"AAPL": "us", "600519": "a-share"}.get
    resolver.normalize_symbol.side_effect = lambda market, token: token
    resolver.currency_for.side_effect = {"us": "USD", "a-share": "CNY"}.get
    fx = MagicMock()
    fx.reference_fx_rate.side_effect = {"USD": 7.18, "CNY": 1.0}.get
    service = ComparisonService(repo, MagicMock(), resolver, fx)
    result = service.compare("AAPL,600519")
    assert result["total"] == 2
    assert fx.reference_fx_rate.call_args_list == [call("USD"), call("CNY")]


def test_compare_skips_unknown_and_no_data():
    repo = MagicMock()
    repo.get_klines.return_value = []
    sync = MagicMock()
    sync.sync.return_value = ([], "mock")
    resolver = MagicMock()
    resolver.detect_market.side_effect = {"AAPL": "us"}.get
    service = ComparisonService(repo, sync, resolver, MagicMock())
    result = service.compare("AAPL,ZZZZ")
    assert result == {"items": [], "total": 0}
    assert sync.sync.called


def test_compare_empty_symbols():
    service = ComparisonService(MagicMock(), MagicMock(), MagicMock(), MagicMock())
    assert service.compare("") == {"items": [], "total": 0}


def test_compare_triggers_sync_when_short():
    repo = MagicMock()
    repo.get_klines.side_effect = [_rows(29), _rows(60)]
    sync = MagicMock()
    sync.sync.return_value = (_rows(), "live")
    resolver = MagicMock()
    resolver.detect_market.return_value = "us"
    resolver.normalize_symbol.return_value = "AAPL"
    resolver.currency_for.return_value = "USD"
    fx = MagicMock()
    fx.reference_fx_rate.return_value = 7.18
    service = ComparisonService(repo, sync, resolver, fx)
    result = service.compare("AAPL")
    assert result["total"] == 1
    assert sync.sync.called
