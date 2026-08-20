"""推荐引擎注册表。"""
from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.engines.weighted import WeightedEngine

ENGINE_REGISTRY: dict[str, type[RecommendationEngine]] = {
    "weighted": WeightedEngine,
}
