"""跨标的同市场截面评分测试。"""
from core.algorithms.config import build_engine
from core.algorithms.context import AnalysisContext


def _ctx(symbol, closes):
    klines = [{"time": f"d{i}", "close": c, "open": c, "high": c, "low": c, "volume": 1000}
              for i, c in enumerate(closes)]
    return AnalysisContext(symbol=symbol, market="a-share", currency="CNY",
                           klines=klines, macro_bias=60.0, news_sentiment=0.0)


def test_cross_sectional_distinguishes_strong_vs_weak():
    # 强标的：单调上涨；弱标的：单调下跌。两者内部因子应被截面 z-score 区分开
    strong = _ctx("STRONG", [100 + i for i in range(60)])
    weak = _ctx("WEAK", [100 - i * 0.5 for i in range(60)])
    engine = build_engine()
    results = engine.score_cross_sectional([strong, weak])
    by_symbol = {r["symbol"]: r for r in results}
    assert by_symbol["STRONG"]["total_score"] > by_symbol["WEAK"]["total_score"]


def test_cross_sectional_returns_all_symbols():
    engine = build_engine()
    ctxs = [_ctx("A", [100 + i for i in range(60)]),
            _ctx("B", [100 + i * 0.3 for i in range(60)]),
            _ctx("C", [100 for _ in range(60)])]
    results = engine.score_cross_sectional(ctxs)
    assert len(results) == 3
    assert {r["symbol"] for r in results} == {"A", "B", "C"}


def test_cross_sectional_factor_z_scores_zero_mean():
    engine = build_engine()
    ctxs = [_ctx("A", [100 + i for i in range(60)]),
            _ctx("B", [100 + i * 0.3 for i in range(60)])]
    results = engine.score_cross_sectional(ctxs)
    # 任意一个因子的 z-score 在两个标的间均值应为 0
    fname = "trend"
    zs = [r["factor_z_scores"][fname] for r in results]
    assert abs(sum(zs) / len(zs)) < 1e-6
