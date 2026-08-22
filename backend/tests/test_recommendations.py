"""首页推荐候选池测试。"""
from unittest.mock import patch

from core import search
from core import screener
from core.universe import MARKETS, UNIVERSE


def _klines(days: int = 60) -> list[dict]:
    rows = []
    for index in range(days):
        close = 100 + index * 0.2
        rows.append(
            {
                "time": f"2026-01-{index + 1:02d}",
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1_000_000,
            }
        )
    return rows


def _fake_candidates() -> dict[str, list[dict]]:
    return {
        market["id"]: [
            {
                "symbol": f"FAKE{index}",
                "name": f"测试{market['name']}",
                "market": market["id"],
                "currency": market["currency"],
                "sector": "未分类",
                "base_risk": 0.5,
                "liquidity": 0.8,
            }
        ]
        for index, market in enumerate(MARKETS)
    }


def test_recommend_uses_dynamic_candidates():
    search._DAILY_CACHE.clear()
    fake = _fake_candidates()
    with patch.object(
        screener,
        "list_candidates",
        side_effect=lambda market, top_n: fake[market][:top_n],
    ), patch.object(screener, "get_kline", return_value=_klines()):
        result = screener.recommend(limit=10, candidates_per_market=1)
    assert result["total_universe"] == len(MARKETS)
    assert {item["market"] for item in result["items"]} == {m["id"] for m in MARKETS}


def test_recommend_default_keeps_builtin_universe():
    search._DAILY_CACHE.clear()
    with patch.object(screener, "get_kline", return_value=_klines()):
        result = screener.recommend(limit=5)
    assert result["total_universe"] == len(UNIVERSE)
    assert len(result["items"]) <= 5
