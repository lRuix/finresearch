"""akshare kline source tests."""
from __future__ import annotations

import pandas as pd

from etl.sources import akshare


def test_fetch_klines_preserves_a_share_fields_and_filters(monkeypatch):
    frame = pd.DataFrame(
        {
            "日期": ["2026-08-22", "2026-08-23", "2026-08-24"],
            "开盘": [100.0, 101.0, 102.0],
            "最高": [101.0, 102.0, 103.0],
            "最低": [99.0, 100.0, 101.0],
            "收盘": [100.5, 101.5, 102.5],
            "成交量": [1000, 1100, 1200],
            "成交额": [1e8, 1.1e8, 1.2e8],
            "振幅": [2.0, 2.5, 3.0],
            "涨跌幅": [1.0, 1.5, 2.0],
            "涨跌额": [1.0, 1.5, 2.0],
            "换手率": [0.8, 0.9, 1.0],
        }
    )

    class FakeAk:
        def stock_zh_a_hist(self, **kwargs):
            return frame

    monkeypatch.setattr(akshare, "_ak", lambda: FakeAk())

    rows = akshare.fetch_klines(
        "a-share",
        "600519",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23"
    assert rows[0]["close"] == 101.5
    assert rows[0]["amount"] == 1.1e8
    assert rows[0]["change_pct"] == 1.5
    assert rows[0]["turnover_rate"] == 0.9
    assert rows[0]["amplitude"] == 2.5


def test_fetch_klines_preserves_open_fund_fields_and_filters(monkeypatch):
    frame = pd.DataFrame(
        {
            "净值日期": ["2026-08-22", "2026-08-23", "2026-08-24"],
            "单位净值": [2.92, 2.95, 2.90],
            "累计净值": [2.916, 2.946, 2.896],
            "日增长率": [0.50, 1.02, -1.33],
            "申购状态": ["开放申购", "开放申购", "开放申购"],
            "赎回状态": ["开放赎回", "开放赎回", "开放赎回"],
        }
    )

    class FakeAk:
        def fund_open_fund_info_em(self, **kwargs):
            return frame

    monkeypatch.setattr(akshare, "_ak", lambda: FakeAk())

    rows = akshare.fetch_klines(
        "fund",
        "110022",
        "d",
        start="2026-08-23",
        end="2026-08-23",
    )

    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-23"
    assert rows[0]["nav"] == 2.95
    assert rows[0]["accum_nav"] == 2.946
    assert rows[0]["daily_growth_pct"] == 1.02
    assert rows[0]["purchase_status"] == "开放申购"
    assert rows[0]["redeem_status"] == "开放赎回"
