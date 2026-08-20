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
    providers._dead_providers.pop("fx:live-rates", None)


def test_reference_fx_rate_falls_back_on_failure():
    # 实时查询失败 → 回退静态值 7.18
    with patch.object(providers, "get_live_fx_rates", return_value=None):
        assert currency.reference_fx_rate("USD") == 7.18


def test_reference_fx_rate_uses_live_when_available():
    fake = {"USD": 6.72, "CNY": 1.0}
    with patch.object(providers, "get_live_fx_rates", return_value=fake):
        assert abs(currency.reference_fx_rate("USD") - 6.72) < 1e-6


def test_get_live_fx_rates_returns_none_on_network_error():
    with patch.object(providers, "_get_json", side_effect=Exception("boom")):
        assert providers.get_live_fx_rates() is None
    providers._dead_providers.pop("fx:live-rates", None)


def test_get_live_fx_rates_marks_dead_on_failure():
    with patch.object(providers, "_get_json", side_effect=Exception("boom")):
        providers.get_live_fx_rates()
    # 熔断后再次调用应直接返回 None（不再次请求）
    with patch.object(providers, "_get_json") as mock_get:
        mock_get.return_value = {"rates": {"CNY": 6.72}}
        # _mark_dead 有 120 秒有效期，手动确保熔断状态已生效
        providers._mark_dead("fx:live-rates")
        assert providers.get_live_fx_rates() is None
        mock_get.assert_not_called()
    providers._dead_providers.pop("fx:live-rates", None)
