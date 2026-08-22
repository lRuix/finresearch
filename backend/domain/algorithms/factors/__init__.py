"""因子注册表。"""
from domain.algorithms.factors.base import Factor
from domain.algorithms.factors.trend import TrendFactor
from domain.algorithms.factors.momentum import MomentumFactor
from domain.algorithms.factors.volatility import VolatilityFactor
from domain.algorithms.factors.risk import RiskFactor
from domain.algorithms.factors.macro import MacroFactor

FACTOR_REGISTRY: dict[str, type[Factor]] = {
    "trend": TrendFactor,
    "momentum": MomentumFactor,
    "volatility": VolatilityFactor,
    "risk": RiskFactor,
    "macro": MacroFactor,
}
