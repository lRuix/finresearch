"""计价与约束层测试。"""
from core.valuation.constraints import QUOTA_USD_YEARLY, quota_note, requires_quota
from core.valuation.currency import market_fx_rate, to_rmb_returns


def test_cny_no_conversion():
    assert market_fx_rate("a-share", "CNY") == 1.0
    assert market_fx_rate("fund", "CNY") == 1.0


def test_to_rmb_returns_applies_fx_change():
    # 本币收益 +10%，汇率升值 +5% → RMB 收益 = 1.10 * 1.05 - 1 = 0.155
    result = to_rmb_returns([0.10], 0.05)
    assert abs(result[0] - 0.155) < 1e-9


def test_to_rmb_returns_no_fx_change():
    result = to_rmb_returns([0.10], 0.0)
    assert abs(result[0] - 0.10) < 1e-9


def test_requires_quota():
    assert requires_quota("us") is True
    assert requires_quota("hk") is True
    assert requires_quota("kr") is True
    assert requires_quota("fx") is True
    assert requires_quota("crypto") is True
    assert requires_quota("a-share") is False
    assert requires_quota("fund") is False


def test_quota_note():
    assert "5 万" in quota_note(QUOTA_USD_YEARLY)
    assert "超" in quota_note(QUOTA_USD_YEARLY + 1)
    assert "剩余" in quota_note(QUOTA_USD_YEARLY - 1000)
