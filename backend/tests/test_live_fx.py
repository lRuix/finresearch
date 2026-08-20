"""实时汇率查询测试。"""
from unittest.mock import patch

from core import providers
from core.valuation import currency


def test_get_live_fx_rates_converts_to_rmb():
    fake = {"base": "USD", "rates": {"CNY": 6.72, "HKD": 7.84, "KRW": 1396.0}}
    with patch.object(providers, "_get_json", return_value=fake):
        rates = providers.get_live_fx_rates()
    assert rates is not None
    assert abs(rates["USD"] - 6.72) < 1e-6
    assert abs(rates["HKD"] - 6.72 / 7.84) < 1e-6
    assert abs(rates["KRW"] - 6.72 / 1396.0) < 1e-6
    assert rates["CNY"] == 1.0
    assert rates["USDT"] == 6.72


def test_get_live_fx_rates_returns_none_on_empty():
    with patch.object(providers, "_get_json", return_value={"rates": {}}):
        assert providers.get_live_fx_rates() is None


def test_reference_fx_rate_falls_back_on_failure():
    # 实时查询失败 → 回退静态值 7.18
    with patch.object(providers, "get_live_fx_rates", return_value=None):
        assert currency.reference_fx_rate("USD") == 7.18


def test_reference_fx_rate_uses_live_when_available():
    fake = {"USD": 6.72, "CNY": 1.0}
    with patch.object(providers, "get_live_fx_rates", return_value=fake):
        assert abs(currency.reference_fx_rate("USD") - 6.72) < 1e-6
