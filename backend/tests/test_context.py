"""AnalysisContext 数据契约测试。"""
from core.algorithms.context import AnalysisContext


def test_context_holds_all_fields():
    ctx = AnalysisContext(
        symbol="688836",
        market="a-share",
        currency="CNY",
        klines=[{"time": "2026-08-19", "close": 845.0}],
        macro_bias=58.0,
        news_sentiment=0.2,
        fx_rate=None,
        horizon="short",
    )
    assert ctx.symbol == "688836"
    assert ctx.fx_rate is None
    assert ctx.horizon == "short"


def test_context_defaults():
    ctx = AnalysisContext(symbol="AAPL", market="us", currency="USD", klines=[])
    assert ctx.macro_bias == 55.0
    assert ctx.news_sentiment == 0.0
    assert ctx.fx_rate is None
    assert ctx.horizon == "short"
