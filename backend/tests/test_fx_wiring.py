"""RMB 计价接线测试。"""
import pytest

from domain.valuation.currency import to_rmb_closes
from infrastructure.datasources.provider_impl import get_live_fx_rates


def test_to_rmb_closes_scales_prices():
    closes = [100.0, 110.0, 90.0]
    rmb = to_rmb_closes(closes, 7.18)
    assert rmb[0] == pytest.approx(718.0)
    assert rmb[1] == pytest.approx(789.8)
    assert rmb[2] == pytest.approx(646.2)


def test_to_rmb_closes_cny_identity():
    closes = [100.0, 200.0]
    assert to_rmb_closes(closes, 1.0) == closes


def test_live_fx_rate_entrypoint_available():
    assert callable(get_live_fx_rates)
