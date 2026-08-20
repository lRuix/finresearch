"""情绪分析注册表。"""
from core.algorithms.sentiment.base import SentimentAnalyzer
from core.algorithms.sentiment.news_rule import NewsRuleAnalyzer

SENTIMENT_REGISTRY: dict[str, type[SentimentAnalyzer]] = {
    "news_rule": NewsRuleAnalyzer,
}
