"""RMB 计价接线测试。"""
import pytest

from core.valuation.currency import reference_fx_rate, to_rmb_closes
from core.search import currency_for


def test_to_rmb_closes_scales_prices():
    closes = [100.0, 110.0, 90.0]
    rmb = to_rmb_closes(closes, 7.18)
    assert rmb[0] == pytest.approx(718.0)
    assert rmb[1] == pytest.approx(789.8)
    assert rmb[2] == pytest.approx(646.2)


def test_to_rmb_closes_cny_identity():
    closes = [100.0, 200.0]
    assert to_rmb_closes(closes, 1.0) == closes


def test_reference_fx_rate_known():
    assert reference_fx_rate("CNY") == 1.0
    assert reference_fx_rate("USD") == 7.18
    assert reference_fx_rate("KRW") == 0.0053


def test_reference_fx_rate_unknown_falls_back():
    assert reference_fx_rate("XYZ") == 1.0


def test_currency_for_all_markets():
    assert currency_for("a-share") == "CNY"
    assert currency_for("fund") == "CNY"
    assert currency_for("us") == "USD"
    assert currency_for("kr") == "KRW"
    assert currency_for("hk") == "HKD"
    assert currency_for("fx") == "MULTI"
    assert currency_for("crypto") == "USDT"
