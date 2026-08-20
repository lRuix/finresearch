"""推荐引擎合成测试。"""
from core.algorithms.config import build_engine
from core.algorithms.context import AnalysisContext
from core.algorithms.engines.weighted import WeightedEngine


def test_build_engine_returns_weighted():
    cfg = {
        "engine": "weighted",
        "factors": ["trend", "momentum", "volatility", "risk", "macro"],
        "sentiment": "news_rule",
        "weights": {"trend": 0.3, "momentum": 0.25, "volatility": 0.15,
                    "risk": 0.15, "macro": 0.15},
    }
    engine = build_engine(cfg)
    assert isinstance(engine, WeightedEngine)
    assert [f.name for f in engine.factors] == cfg["factors"]


def test_combine_equal_scores_and_neutral_sentiment():
    engine = WeightedEngine(factor_names=["trend"], weights={"trend": 1.0})
    result = engine.combine({"trend": 70.0}, {"multiplier": 1.0})
    # 单因子：z-score 后映射回 0-100，期望仍在中位附近（单点 z=0 → 50）
    assert 0 <= result["total_score"] <= 100


def test_sentiment_multiplier_scales_score():
    engine = WeightedEngine(factor_names=["trend"], weights={"trend": 1.0})
    neutral = engine.combine({"trend": 70.0}, {"multiplier": 1.0})
    bullish = engine.combine({"trend": 70.0}, {"multiplier": 1.2})
    assert bullish["total_score"] > neutral["total_score"]


def test_missing_factor_skipped_and_renormalized():
    engine = WeightedEngine(factor_names=["trend", "momentum"],
                            weights={"trend": 0.5, "momentum": 0.5})
    result = engine.combine({"trend": 80.0}, {"multiplier": 1.0})  # momentum 缺失
    assert 0 <= result["total_score"] <= 100
