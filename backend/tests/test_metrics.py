"""风险调整后收益指标测试。"""
from core.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


def _rising_closes():
    return [100.0 + i for i in range(60)]


def _falling_closes():
    return [100.0 - i for i in range(20)]


def test_max_drawdown_zero_on_rise():
    assert max_drawdown(_rising_closes()) == 0.0


def test_max_drawdown_positive_on_fall():
    md = max_drawdown(_falling_closes())
    assert md > 0.0
    assert md < 1.0


def test_annualized_return_positive_on_rise():
    r = annualized_return(_rising_closes())
    assert r > 0.0


def test_calmar_ratio_raises_on_zero_drawdown():
    # 无回撤时卡玛比率无法定义，返回 None 而非报错
    result = calmar_ratio(_rising_closes())
    assert result is None


def test_calmar_ratio_computed_on_fall():
    result = calmar_ratio(_falling_closes())
    assert result is not None
    assert result < 0  # 亏损 + 回撤 → 负卡玛


def test_sharpe_ratio_positive_on_rise():
    result = sharpe_ratio(_rising_closes())
    assert result > 0.0
