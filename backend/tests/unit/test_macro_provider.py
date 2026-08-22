"""MacroNewsProvider adapter tests."""
from infrastructure.datasources.macro_provider import MacroNewsProvider


def test_market_bias_and_score():
    provider = MacroNewsProvider()
    assert isinstance(provider.market_bias("us"), (dict, type(None)))
    assert 0 <= provider.macro_score("us") <= 100


def test_news_items_filtered_by_market():
    provider = MacroNewsProvider()
    items = provider.news_items("us")
    assert isinstance(items, list)
    wanted = {"美股", "利率", "美元", "全球"}
    assert all(set(item["tags"]) & wanted for item in items)
    unrelated = {"A股", "韩股", "南向资金", "数字货币"}
    assert all(not (set(item["tags"]) & unrelated) for item in items)
