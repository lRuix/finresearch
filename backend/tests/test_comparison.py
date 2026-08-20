"""跨资产比较编排测试。"""
from core.comparison import compare_assets


def _rising(n=60):
    return [100.0 + i for i in range(n)]


def _falling(n=60):
    return [100.0 - i * 0.5 for i in range(n)]


def test_compare_assets_sorts_by_calmar_desc():
    assets = [
        {"symbol": "RISING", "name": "上涨标的", "market": "us", "currency": "USD",
         "rmb_closes": _rising()},
        {"symbol": "FALL", "name": "下跌标的", "market": "hk", "currency": "HKD",
         "rmb_closes": _falling()},
    ]
    result = compare_assets(assets)
    assert len(result) == 2
    # 上涨标的卡玛为 None（无回撤），应排后；下跌标的负卡玛排前？——按 None 置底规则
    assert result[0]["symbol"] == "FALL"  # 有回撤的参与排序，None 置底
    assert result[1]["calmar_ratio"] is None


def test_compare_assets_marks_quota():
    assets = [
        {"symbol": "A", "name": "A股", "market": "a-share", "currency": "CNY",
         "rmb_closes": _rising()},
        {"symbol": "US", "name": "美股", "market": "us", "currency": "USD",
         "rmb_closes": _falling()},
    ]
    result = compare_assets(assets)
    by_symbol = {r["symbol"]: r for r in result}
    assert by_symbol["A"]["requires_quota"] is False
    assert by_symbol["US"]["requires_quota"] is True
    assert by_symbol["US"]["quota_note"] != ""


def test_compare_assets_empty():
    assert compare_assets([]) == []
