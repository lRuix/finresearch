"""因子打分测试。"""
import pytest
from core.algorithms.context import AnalysisContext
from core.algorithms.factors import (
    TrendFactor,
    MomentumFactor,
    VolatilityFactor,
    RiskFactor,
    MacroFactor,
)


def _uptrend_klines():
    # 20 根单调上涨 K 线，close 从 100 涨到 119
    return [
        {"time": f"2026-07-{i+1:02d}", "open": 100 + i, "high": 101 + i,
         "low": 99 + i, "close": 100 + i, "volume": 1000}
        for i in range(20)
    ]


@pytest.fixture
def uptrend_ctx():
    return AnalysisContext(
        symbol="TEST", market="a-share", currency="CNY",
        klines=_uptrend_klines(), macro_bias=70.0, news_sentiment=0.3,
    )


def test_trend_factor_score_range(uptrend_ctx):
    result = TrendFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_trend_factor_detects_uptrend(uptrend_ctx):
    result = TrendFactor().score(uptrend_ctx)
    assert result["score"] >= 80  # 单调上涨，均线多头排列


def test_momentum_factor_range(uptrend_ctx):
    result = MomentumFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_volatility_factor_range(uptrend_ctx):
    result = VolatilityFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_risk_factor_range(uptrend_ctx):
    result = RiskFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_macro_factor_uses_bias(uptrend_ctx):
    result = MacroFactor().score(uptrend_ctx)
    assert result["score"] == 70.0
