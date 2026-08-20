"""因子注册表。"""
from core.algorithms.factors.base import Factor
from core.algorithms.factors.trend import TrendFactor
from core.algorithms.factors.momentum import MomentumFactor
from core.algorithms.factors.volatility import VolatilityFactor
from core.algorithms.factors.risk import RiskFactor
from core.algorithms.factors.macro import MacroFactor

FACTOR_REGISTRY: dict[str, type[Factor]] = {
    "trend": TrendFactor,
    "momentum": MomentumFactor,
    "volatility": VolatilityFactor,
    "risk": RiskFactor,
    "macro": MacroFactor,
}
