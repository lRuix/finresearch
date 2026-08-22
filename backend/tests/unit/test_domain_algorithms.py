"""Domain algorithms smoke tests."""
from domain.algorithms.config import build_engine
from domain.algorithms.context import AnalysisContext


def test_build_engine_and_score():
    engine = build_engine()
    ctx = AnalysisContext(
        symbol="AAPL",
        market="us",
        currency="USD",
        klines=[
            {"time": f"2026-08-{i:02d}", "close": 100.0 + i}
            for i in range(1, 61)
        ],
        macro_bias=58.0,
        news_sentiment=0.1,
        fx_rate=7.18,
        horizon="short",
    )
    factor_scores = {factor.name: factor.score(ctx)["score"] for factor in engine.factors}
    combined = engine.combine(factor_scores, engine.sentiment.analyze(ctx))
    assert 0 <= combined["total_score"] <= 100
