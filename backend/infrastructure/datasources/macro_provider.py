"""Macro/news adapter wrapping core.macro static data."""
from __future__ import annotations

from core import macro


_MARKET_TAGS = {
    "a-share": {"A股", "政策", "信用"},
    "fund": {"A股", "政策", "ETF"},
    "us": {"美股", "利率", "美元", "全球"},
    "kr": {"韩股", "半导体", "汇率", "全球"},
    "hk": {"港股", "南向资金", "政策"},
    "fx": {"汇率", "美元", "利率", "全球"},
    "crypto": {"数字货币", "ETF", "全球"},
}


class MacroNewsProvider:
    def market_bias(self, market: str) -> dict | None:
        return macro.MARKET_BIAS.get(market)

    def macro_score(self, market: str) -> float:
        return macro.macro_score_for(market)

    def news_items(self, market: str) -> list[dict]:
        wanted = _MARKET_TAGS.get(market, {"全球"})
        return [item for item in macro.NEWS_ITEMS if set(item["tags"]) & wanted]
