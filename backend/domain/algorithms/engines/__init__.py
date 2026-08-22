"""推荐引擎注册表。"""
from domain.algorithms.engines.base import RecommendationEngine
from domain.algorithms.engines.weighted import WeightedEngine

ENGINE_REGISTRY: dict[str, type[RecommendationEngine]] = {
    "weighted": WeightedEngine,
}
