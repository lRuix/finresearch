"""情绪分析测试。"""
from core.algorithms.context import AnalysisContext
from core.algorithms.sentiment import NewsRuleAnalyzer


def test_multiplier_neutral_when_zero():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=0.0)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert result["multiplier"] == 1.0
    assert result["polarity"] == 0.0


def test_multiplier_positive():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=0.5)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert abs(result["multiplier"] - 1.1) < 1e-9  # 1 + 0.2 * 0.5
    assert result["polarity"] == 0.5


def test_multiplier_negative_clamped():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=-1.0)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert result["multiplier"] == 0.8
