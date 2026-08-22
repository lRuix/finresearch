"""情绪分析注册表。"""
from domain.algorithms.sentiment.base import SentimentAnalyzer
from domain.algorithms.sentiment.news_rule import NewsRuleAnalyzer

SENTIMENT_REGISTRY: dict[str, type[SentimentAnalyzer]] = {
    "news_rule": NewsRuleAnalyzer,
}
