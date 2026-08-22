"""实时汇率查询测试。"""
from unittest.mock import patch

import pytest

from infrastructure.datasources import provider_impl


@pytest.fixture(autouse=True)
def _clear_provider_circuit_breaker():
    """其他测试可能触发真实请求失败并留下熔断状态，逐例清理保证隔离。"""
    provider_impl._dead_providers.clear()
    yield
    provider_impl._dead_providers.clear()


def test_get_live_fx_rates_converts_to_rmb():
    fake = {"base": "USD", "rates": {"CNY": 6.72, "HKD": 7.84, "KRW": 1396.0}}
    with patch.object(provider_impl, "_get_json", return_value=fake):
        rates = provider_impl.get_live_fx_rates()
    assert rates is not None
    assert abs(rates["USD"] - 6.72) < 1e-6
    assert abs(rates["HKD"] - 6.72 / 7.84) < 1e-6
    assert abs(rates["KRW"] - 6.72 / 1396.0) < 1e-6
    assert rates["CNY"] == 1.0
    assert rates["USDT"] == 6.72


def test_get_live_fx_rates_returns_none_on_empty():
    with patch.object(provider_impl, "_get_json", return_value={"rates": {}}):
        assert provider_impl.get_live_fx_rates() is None
    provider_impl._dead_providers.pop("fx:live-rates", None)


def test_get_live_fx_rates_returns_none_on_network_error():
    with patch.object(provider_impl, "_get_json", side_effect=Exception("boom")):
        assert provider_impl.get_live_fx_rates() is None
    provider_impl._dead_providers.pop("fx:live-rates", None)


def test_get_live_fx_rates_marks_dead_on_failure():
    with patch.object(provider_impl, "_get_json", side_effect=Exception("boom")):
        provider_impl.get_live_fx_rates()
    # 熔断后再次调用应直接返回 None（不再次请求）
    with patch.object(provider_impl, "_get_json") as mock_get:
        mock_get.return_value = {"rates": {"CNY": 6.72}}
        # _mark_dead 有 120 秒有效期，手动确保熔断状态已生效
        provider_impl._mark_dead("fx:live-rates")
        assert provider_impl.get_live_fx_rates() is None
        mock_get.assert_not_called()
    provider_impl._dead_providers.pop("fx:live-rates", None)
