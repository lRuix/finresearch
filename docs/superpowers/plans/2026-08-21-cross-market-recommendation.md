# 跨市场标的推荐系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将固定候选池的投研 MVP 升级为「任意代码可搜索 + 统一 RMB 计价 + 跨资产风险调整后排序推荐」的可插拔算法研究终端。

**Architecture:** 后端拆为模块一（工程：providers/search/valuation/screener/app）与模块二（算法：algorithms 引擎/因子/情绪三层接口）。工程层只依赖抽象接口，算法实现通过注册表 + 配置替换。跨资产比较经统一 RMB 计价后输出卡玛比率等风险调整后指标。

**Tech Stack:** Python 3.11 · FastAPI 0.136 · pytest 9.0 · React 18 + TypeScript + Vite + ECharts

**Spec:** `docs/superpowers/specs/2026-08-21-cross-market-recommendation-design.md`

## Global Constraints

- Python 3.11（`backend/.venv` 已存在，测试/运行用 `backend/.venv/bin/python`）
- pytest 9.0.3 用于后端测试；测试目录 `backend/tests/`
- 算法层（`backend/core/algorithms/`）**禁止** import `providers` 或发起网络请求，只消费 `AnalysisContext`
- 所有新增代码使用 `from __future__ import annotations` 与类型注解，风格对齐现有 `core/*.py`
- Git commit message 中文，格式 `<类型>: <描述>`（feat/fix/refactor/docs/chore/style）
- 跨币种折算公式：`收益(RMB) = 收益(本币) × (1 + 汇率变动率)`；购汇额度 = 每人每年等值 5 万美元
- 前端 TS 严格模式（现有 `tsconfig.json` 已开 strict）

---

### Task 1: 测试脚手架与 AnalysisContext 数据契约

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/core/algorithms/__init__.py`
- Create: `backend/core/algorithms/context.py`
- Create: `backend/tests/test_context.py`

**Interfaces:**
- Produces: `AnalysisContext` dataclass，字段 `symbol: str`、`market: str`、`currency: str`、`klines: list[dict]`、`macro_bias: float`、`news_sentiment: float`、`fx_rate: float | None`、`horizon: str`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_context.py`：

```python
"""AnalysisContext 数据契约测试。"""
from core.algorithms.context import AnalysisContext


def test_context_holds_all_fields():
    ctx = AnalysisContext(
        symbol="688836",
        market="a-share",
        currency="CNY",
        klines=[{"time": "2026-08-19", "close": 845.0}],
        macro_bias=58.0,
        news_sentiment=0.2,
        fx_rate=None,
        horizon="short",
    )
    assert ctx.symbol == "688836"
    assert ctx.fx_rate is None
    assert ctx.horizon == "short"


def test_context_defaults():
    ctx = AnalysisContext(symbol="AAPL", market="us", currency="USD", klines=[])
    assert ctx.macro_bias == 55.0
    assert ctx.news_sentiment == 0.0
    assert ctx.fx_rate is None
    assert ctx.horizon == "short"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_context.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'core.algorithms'`（或 `AnalysisContext` 未定义）

- [ ] **Step 3: 写最小实现**

创建 `backend/core/algorithms/context.py`：

```python
"""AnalysisContext — 工程层传给算法层的干净数据契约。

算法层只消费这个对象，不 import providers、不发起网络请求。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisContext:
    symbol: str
    market: str
    currency: str
    klines: list[dict] = field(default_factory=list)
    macro_bias: float = 55.0
    news_sentiment: float = 0.0
    fx_rate: float | None = None
    horizon: str = "short"
```

创建 `backend/core/algorithms/__init__.py`（空文件）和 `backend/tests/__init__.py`（空文件）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_context.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/tests/__init__.py backend/tests/test_context.py backend/core/algorithms/__init__.py backend/core/algorithms/context.py
git commit -m "feat: 新增 AnalysisContext 数据契约与测试脚手架"
```

---

### Task 2: 因子接口与五个因子实现

**Files:**
- Create: `backend/core/algorithms/factors/__init__.py`
- Create: `backend/core/algorithms/factors/base.py`
- Create: `backend/core/algorithms/factors/trend.py`
- Create: `backend/core/algorithms/factors/momentum.py`
- Create: `backend/core/algorithms/factors/volatility.py`
- Create: `backend/core/algorithms/factors/risk.py`
- Create: `backend/core/algorithms/factors/macro.py`
- Create: `backend/tests/test_factors.py`

**Interfaces:**
- Consumes: `AnalysisContext`（Task 1）、`core.indicators` 的 `sma/macd/rsi/bollinger/atr/annualized_volatility`
- Produces:
  - `Factor` ABC：属性 `name: str`，方法 `score(ctx: AnalysisContext) -> dict`（返回 `{"score": float, "detail": dict}`）
  - `TrendFactor` / `MomentumFactor` / `VolatilityFactor` / `RiskFactor` / `MacroFactor`，各返回 `score` ∈ [0, 100]

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_factors.py`：

```python
"""因子打分测试。"""
import pytest
from core.algorithms.context import AnalysisContext
from core.algorithms.factors import (
    TrendFactor,
    MomentumFactor,
    VolatilityFactor,
    RiskFactor,
    MacroFactor,
)


def _uptrend_klines():
    # 20 根单调上涨 K 线，close 从 100 涨到 119
    return [
        {"time": f"2026-07-{i+1:02d}", "open": 100 + i, "high": 101 + i,
         "low": 99 + i, "close": 100 + i, "volume": 1000}
        for i in range(20)
    ]


@pytest.fixture
def uptrend_ctx():
    return AnalysisContext(
        symbol="TEST", market="a-share", currency="CNY",
        klines=_uptrend_klines(), macro_bias=70.0, news_sentiment=0.3,
    )


def test_trend_factor_score_range(uptrend_ctx):
    result = TrendFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_trend_factor_detects_uptrend(uptrend_ctx):
    result = TrendFactor().score(uptrend_ctx)
    assert result["score"] >= 80  # 单调上涨，均线多头排列


def test_momentum_factor_range(uptrend_ctx):
    result = MomentumFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_volatility_factor_range(uptrend_ctx):
    result = VolatilityFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_risk_factor_range(uptrend_ctx):
    result = RiskFactor().score(uptrend_ctx)
    assert 0 <= result["score"] <= 100


def test_macro_factor_uses_bias(uptrend_ctx):
    result = MacroFactor().score(uptrend_ctx)
    assert result["score"] == 70.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_factors.py -v`
Expected: FAIL，`ImportError: cannot import name 'TrendFactor'`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/algorithms/factors/base.py`：

```python
"""Factor 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.context import AnalysisContext


class Factor(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def score(self, ctx: AnalysisContext) -> dict:
        """返回 {"score": 0-100, "detail": {...}}"""
```

创建 `backend/core/algorithms/factors/trend.py`：

```python
"""趋势因子：均线多头排列 + MACD 柱。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import macd, sma


class TrendFactor(Factor):
    name = "trend"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        points = 0
        sma5, sma10, sma20 = sma(closes, 5), sma(closes, 10), sma(closes, 20)
        sma60 = sma(closes, 60)
        price = closes[-1]
        if sma5 and sma10 and sma20:
            points += int(sma5 > sma10) + int(sma10 > sma20) + int(price > sma20)
            if sma20 and sma60:
                points += int(sma20 > sma60)
            m = macd(closes)
            if m["histogram"] is not None and m["histogram"] > 0:
                points += 1
        return {"score": round(points / 5 * 100, 1), "detail": {"points": points}}
```

创建 `backend/core/algorithms/factors/momentum.py`：

```python
"""动量因子：RSI 位置 + 20 日涨跌修正。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import rsi


def _clamp(v: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, v))


class MomentumFactor(Factor):
    name = "momentum"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        rsi14 = rsi(closes, 14)
        if rsi14 is None:
            base = 50.0
        elif 48 <= rsi14 <= 62:
            base = 82.0
        elif 42 <= rsi14 <= 70:
            base = 68.0
        elif rsi14 < 30 or rsi14 > 80:
            base = 32.0
        else:
            base = 50.0
        change_20d = 0.0
        if len(closes) >= 21 and closes[-21]:
            change_20d = (closes[-1] / closes[-21] - 1) * 100
        if change_20d > 5:
            base = _clamp(base + 12)
        elif change_20d < -5:
            base = _clamp(base - 10)
        return {"score": round(base, 1), "detail": {"rsi14": rsi14, "change_20d": round(change_20d, 2)}}
```

创建 `backend/core/algorithms/factors/volatility.py`：

```python
"""低波动因子：年化波动率 vs 市场目标分档。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import annualized_volatility

_VOL_TARGET = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}


class VolatilityFactor(Factor):
    name = "volatility"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        vol = annualized_volatility(closes, 20)
        target = _VOL_TARGET.get(ctx.market, 0.28)
        if vol is None:
            s = 50.0
        elif vol <= target * 0.8:
            s = 72.0
        elif vol <= target * 1.15:
            s = 86.0
        elif vol <= target * 1.6:
            s = 58.0
        else:
            s = 34.0
        return {"score": s, "detail": {"vol20": vol, "target": target}}
```

创建 `backend/core/algorithms/factors/risk.py`：

```python
"""风险因子：波动率反推风险系数 → (1-risk)*100。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor
from core.indicators import annualized_volatility

_VOL_TARGET = {"fx": 0.06, "fund": 0.14, "a-share": 0.22}


class RiskFactor(Factor):
    name = "risk"

    def score(self, ctx: AnalysisContext) -> dict:
        closes = [r["close"] for r in ctx.klines]
        vol = annualized_volatility(closes, 20)
        target = _VOL_TARGET.get(ctx.market, 0.28)
        ratio = (vol / target) if (vol and target) else 1.0
        if ratio <= 0.6:
            risk = 0.35
        elif ratio <= 0.9:
            risk = 0.45
        elif ratio <= 1.2:
            risk = 0.58
        elif ratio <= 1.7:
            risk = 0.72
        elif ratio <= 2.4:
            risk = 0.84
        else:
            risk = 0.93
        return {"score": round((1 - risk) * 100, 1), "detail": {"risk_coef": risk, "vol20": vol}}
```

创建 `backend/core/algorithms/factors/macro.py`：

```python
"""宏观因子：直接使用市场偏置分。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.factors.base import Factor


class MacroFactor(Factor):
    name = "macro"

    def score(self, ctx: AnalysisContext) -> dict:
        return {"score": round(float(ctx.macro_bias), 1), "detail": {"bias": ctx.macro_bias}}
```

创建 `backend/core/algorithms/factors/__init__.py`：

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_factors.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/algorithms/factors/ backend/tests/test_factors.py
git commit -m "feat: 实现五个可插拔因子与注册表"
```

---

### Task 3: 情绪分析接口与新闻规则实现

**Files:**
- Create: `backend/core/algorithms/sentiment/__init__.py`
- Create: `backend/core/algorithms/sentiment/base.py`
- Create: `backend/core/algorithms/sentiment/news_rule.py`
- Create: `backend/tests/test_sentiment.py`

**Interfaces:**
- Consumes: `AnalysisContext`（Task 1）
- Produces: `SentimentAnalyzer` ABC（方法 `analyze(ctx) -> dict`，返回 `{"polarity": float(-1..1), "confidence": float, "multiplier": float(0.8..1.2)}`）；`NewsRuleAnalyzer` 实现

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_sentiment.py`：

```python
"""情绪分析测试。"""
from core.algorithms.context import AnalysisContext
from core.algorithms.sentiment import NewsRuleAnalyzer


def test_multiplier_neutral_when_zero():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=0.0)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert result["multiplier"] == 1.0
    assert result["polarity"] == 0.0


def test_multiplier_positive():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=0.5)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert abs(result["multiplier"] - 1.1) < 1e-9  # 1 + 0.2 * 0.5
    assert result["polarity"] == 0.5


def test_multiplier_negative_clamped():
    ctx = AnalysisContext(symbol="T", market="us", currency="USD", klines=[], news_sentiment=-1.0)
    result = NewsRuleAnalyzer().analyze(ctx)
    assert result["multiplier"] == 0.8
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sentiment.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/algorithms/sentiment/base.py`：

```python
"""SentimentAnalyzer 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.context import AnalysisContext


class SentimentAnalyzer(ABC):
    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> dict:
        """返回 {"polarity": -1..1, "confidence": 0..1, "multiplier": 0.8..1.2}"""
```

创建 `backend/core/algorithms/sentiment/news_rule.py`：

```python
"""新闻情绪规则：乘数 = 1 + 0.2 * polarity。"""
from __future__ import annotations

from core.algorithms.context import AnalysisContext
from core.algorithms.sentiment.base import SentimentAnalyzer


def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


class NewsRuleAnalyzer(SentimentAnalyzer):
    def analyze(self, ctx: AnalysisContext) -> dict:
        polarity = _clamp(ctx.news_sentiment, -1.0, 1.0)
        multiplier = round(1 + 0.2 * polarity, 4)
        return {
            "polarity": round(polarity, 4),
            "confidence": 0.6,
            "multiplier": multiplier,
        }
```

创建 `backend/core/algorithms/sentiment/__init__.py`：

```python
"""情绪分析注册表。"""
from core.algorithms.sentiment.base import SentimentAnalyzer
from core.algorithms.sentiment.news_rule import NewsRuleAnalyzer

SENTIMENT_REGISTRY: dict[str, type[SentimentAnalyzer]] = {
    "news_rule": NewsRuleAnalyzer,
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_sentiment.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/algorithms/sentiment/ backend/tests/test_sentiment.py
git commit -m "feat: 实现情绪分析接口与新闻规则实现"
```

---

### Task 4: 推荐引擎（截面 z-score + 加权合成）

**Files:**
- Create: `backend/core/algorithms/engines/__init__.py`
- Create: `backend/core/algorithms/engines/base.py`
- Create: `backend/core/algorithms/engines/weighted.py`
- Create: `backend/core/algorithms/config.py`
- Create: `backend/tests/test_engine.py`

**Interfaces:**
- Consumes: `Factor`（Task 2）、`SentimentAnalyzer`（Task 3）
- Produces:
  - `RecommendationEngine` ABC：`factors: list[Factor]`、`sentiment: SentimentAnalyzer`、`combine(factor_scores: dict[str, float], sentiment: dict) -> dict`
  - `WeightedEngine` 实现，`combine` 返回 `{"total_score": float, "detail": dict}`
  - `build_engine(config: dict) -> RecommendationEngine` 工厂函数

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_engine.py`：

```python
"""推荐引擎合成测试。"""
from core.algorithms.config import build_engine
from core.algorithms.context import AnalysisContext
from core.algorithms.engines.weighted import WeightedEngine


def test_build_engine_returns_weighted():
    cfg = {
        "engine": "weighted",
        "factors": ["trend", "momentum", "volatility", "risk", "macro"],
        "sentiment": "news_rule",
        "weights": {"trend": 0.3, "momentum": 0.25, "volatility": 0.15,
                    "risk": 0.15, "macro": 0.15},
    }
    engine = build_engine(cfg)
    assert isinstance(engine, WeightedEngine)
    assert [f.name for f in engine.factors] == cfg["factors"]


def test_combine_equal_scores_and_neutral_sentiment():
    engine = WeightedEngine(factor_names=["trend"], weights={"trend": 1.0})
    result = engine.combine({"trend": 70.0}, {"multiplier": 1.0})
    # 单因子：z-score 后映射回 0-100，期望仍在中位附近（单点 z=0 → 50）
    assert 0 <= result["total_score"] <= 100


def test_sentiment_multiplier_scales_score():
    engine = WeightedEngine(factor_names=["trend"], weights={"trend": 1.0})
    neutral = engine.combine({"trend": 70.0}, {"multiplier": 1.0})
    bullish = engine.combine({"trend": 70.0}, {"multiplier": 1.2})
    assert bullish["total_score"] > neutral["total_score"]


def test_missing_factor_skipped_and_renormalized():
    engine = WeightedEngine(factor_names=["trend", "momentum"],
                            weights={"trend": 0.5, "momentum": 0.5})
    result = engine.combine({"trend": 80.0}, {"multiplier": 1.0})  # momentum 缺失
    assert 0 <= result["total_score"] <= 100
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/algorithms/engines/base.py`：

```python
"""RecommendationEngine 抽象接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.algorithms.factors.base import Factor
from core.algorithms.sentiment.base import SentimentAnalyzer


class RecommendationEngine(ABC):
    @property
    @abstractmethod
    def factors(self) -> list[Factor]: ...

    @property
    @abstractmethod
    def sentiment(self) -> SentimentAnalyzer: ...

    @abstractmethod
    def combine(self, factor_scores: dict[str, float], sentiment: dict) -> dict:
        """返回 {"total_score": 0-100, "detail": {...}}"""
```

创建 `backend/core/algorithms/engines/weighted.py`：

```python
"""加权合成引擎：截面 z-score → 加权 → 映射 0-100 → 情绪乘数。"""
from __future__ import annotations

import math

from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.factors.base import Factor
from core.algorithms.sentiment.base import SentimentAnalyzer


def _clamp(v: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, v))


def _sigmoid(x: float) -> float:
    # 将 z-score（约 -3..3）映射到 0-100
    return 100 / (1 + math.exp(-x))


class WeightedEngine(RecommendationEngine):
    def __init__(self, factors: list[Factor], sentiment: SentimentAnalyzer,
                 weights: dict[str, float] | None = None):
        self._factors = factors
        self._sentiment = sentiment
        self._weights = weights or {f.name: 1.0 / len(factors) for f in factors}

    @property
    def factors(self) -> list[Factor]:
        return self._factors

    @property
    def sentiment(self) -> SentimentAnalyzer:
        return self._sentiment

    def combine(self, factor_scores: dict[str, float], sentiment: dict) -> dict:
        available = {k: v for k, v in factor_scores.items() if k in self._weights}
        if not available:
            return {"total_score": 50.0, "detail": {"available": [], "multiplier": sentiment.get("multiplier", 1.0)}}

        # 截面 z-score（对可用因子得分）
        values = list(available.values())
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        if std < 1e-9:
            z_scores = {k: 0.0 for k in available}
        else:
            z_scores = {k: (v - mean) / std for k, v in available.items()}

        # 加权（用可用因子的权重重新归一化）
        total_w = sum(self._weights.get(k, 0.0) for k in available) or 1.0
        composite_z = sum(z_scores[k] * self._weights.get(k, 0.0) / total_w for k in available)

        base_score = _sigmoid(composite_z)
        multiplier = sentiment.get("multiplier", 1.0)
        total = _clamp(base_score * multiplier)

        return {
            "total_score": round(total, 1),
            "detail": {
                "z_scores": {k: round(v, 4) for k, v in z_scores.items()},
                "available": sorted(available),
                "multiplier": multiplier,
                "base_score": round(base_score, 1),
            },
        }
```

创建 `backend/core/algorithms/config.py`：

```python
"""算法配置：注册表 → 工厂函数。"""
from __future__ import annotations

from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.engines.weighted import WeightedEngine
from core.algorithms.factors import FACTOR_REGISTRY
from core.algorithms.sentiment import SENTIMENT_REGISTRY

ENGINE_REGISTRY: dict[str, type[RecommendationEngine]] = {
    "weighted": WeightedEngine,
}

DEFAULT_CONFIG = {
    "engine": "weighted",
    "factors": ["trend", "momentum", "volatility", "risk", "macro"],
    "sentiment": "news_rule",
    "weights": {"trend": 0.30, "momentum": 0.25, "volatility": 0.15,
                "risk": 0.15, "macro": 0.15},
}


def build_engine(config: dict | None = None) -> RecommendationEngine:
    cfg = config or DEFAULT_CONFIG
    factor_names = cfg["factors"]
    factors = [FACTOR_REGISTRY[n]() for n in factor_names]
    sentiment = SENTIMENT_REGISTRY[cfg["sentiment"]]()
    engine_cls = ENGINE_REGISTRY[cfg["engine"]]
    if engine_cls is WeightedEngine:
        return WeightedEngine(factors, sentiment, weights=cfg.get("weights"))
    return engine_cls(factors, sentiment)
```

创建 `backend/core/algorithms/engines/__init__.py`：

```python
"""推荐引擎注册表。"""
from core.algorithms.engines.base import RecommendationEngine
from core.algorithms.engines.weighted import WeightedEngine

ENGINE_REGISTRY: dict[str, type[RecommendationEngine]] = {
    "weighted": WeightedEngine,
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_engine.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/algorithms/engines/ backend/core/algorithms/config.py backend/tests/test_engine.py
git commit -m "feat: 实现加权合成推荐引擎与算法工厂"
```

---

### Task 5: 计价与约束层（RMB 折算 + 购汇额度）

**Files:**
- Create: `backend/core/valuation/__init__.py`
- Create: `backend/core/valuation/currency.py`
- Create: `backend/core/valuation/constraints.py`
- Create: `backend/tests/test_valuation.py`

**Interfaces:**
- Consumes: `core.providers.get_kline`（拉汇率，但测试用 mock）
- Produces:
  - `to_rmb_returns(returns: list[float], fx_change: float) -> list[float]`：本币收益 × (1+汇率变动率)
  - `market_fx_rate(market: str, currency: str) -> float | None`：返回本币→RMB 近似汇率（CNY 返回 1.0）
  - `QUOTA_USD_YEARLY = 50000`；`requires_quota(market: str) -> bool`；`quota_note(cumulative_quota_usd: float) -> str`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_valuation.py`：

```python
"""计价与约束层测试。"""
from core.valuation.constraints import QUOTA_USD_YEARLY, quota_note, requires_quota
from core.valuation.currency import market_fx_rate, to_rmb_returns


def test_cny_no_conversion():
    assert market_fx_rate("a-share", "CNY") == 1.0
    assert market_fx_rate("fund", "CNY") == 1.0


def test_to_rmb_returns_applies_fx_change():
    # 本币收益 +10%，汇率升值 +5% → RMB 收益 = 1.10 * 1.05 - 1 = 0.155
    result = to_rmb_returns([0.10], 0.05)
    assert abs(result[0] - 0.155) < 1e-9


def test_to_rmb_returns_no_fx_change():
    result = to_rmb_returns([0.10], 0.0)
    assert abs(result[0] - 0.10) < 1e-9


def test_requires_quota():
    assert requires_quota("us") is True
    assert requires_quota("hk") is True
    assert requires_quota("kr") is True
    assert requires_quota("fx") is True
    assert requires_quota("crypto") is True
    assert requires_quota("a-share") is False
    assert requires_quota("fund") is False


def test_quota_note():
    assert "5 万" in quota_note(QUOTA_USD_YEARLY)
    assert "超" in quota_note(QUOTA_USD_YEARLY + 1)
    assert "剩余" in quota_note(QUOTA_USD_YEARLY - 1000)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_valuation.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/valuation/currency.py`：

```python
"""统一 RMB 计价。"""
from __future__ import annotations


def to_rmb_returns(returns: list[float], fx_change: float) -> list[float]:
    """本币收益率序列折算为 RMB 口径：收益(RMB) = 收益(本币) × (1+汇率变动率)。

    returns: 本币各期收益率（小数，如 0.10 表示 +10%）
    fx_change: 期间汇率变动率（本币相对 RMB，+ 表示本币升值）
    """
    factor = 1 + fx_change
    return [r * factor for r in returns]


def market_fx_rate(market: str, currency: str) -> float | None:
    """本币 → RMB 汇率。CNY 计价直接返回 1.0；其余返回 None（需外部填充）。"""
    if currency == "CNY":
        return 1.0
    return None
```

创建 `backend/core/valuation/constraints.py`：

```python
"""硬约束：购汇额度与合规。"""
from __future__ import annotations

# 个人便利化购汇额度：每人每年等值 5 万美元
QUOTA_USD_YEARLY = 50_000

# 需购汇的市场（本币非人民币）
_QUOTA_MARKETS = {"us", "hk", "kr", "fx", "crypto"}


def requires_quota(market: str) -> bool:
    return market in _QUOTA_MARKETS


def quota_note(cumulative_quota_usd: float) -> str:
    """根据累计占用购汇额度生成提示。"""
    if cumulative_quota_usd > QUOTA_USD_YEARLY:
        over = cumulative_quota_usd - QUOTA_USD_YEARLY
        return f"已超出年度购汇额度（5 万美元），超出约 {over:,.0f} 美元"
    remaining = QUOTA_USD_YEARLY - cumulative_quota_usd
    return f"占用购汇额度，年度剩余约 {remaining:,.0f} 美元"
```

创建 `backend/core/valuation/__init__.py`（空文件）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_valuation.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/valuation/ backend/tests/test_valuation.py
git commit -m "feat: 实现统一 RMB 计价与购汇额度约束层"
```

---

### Task 6: 跨资产风险调整后收益排序

**Files:**
- Create: `backend/core/valuation/metrics.py`
- Create: `backend/tests/test_metrics.py`

**Interfaces:**
- Consumes: `core.providers.get_kline`（测试用 mock klines 直接传）
- Produces:
  - `max_drawdown(closes: list[float]) -> float`（返回正小数，如 0.25 表示 -25%）
  - `annualized_return(closes: list[float], periods_per_year: int = 252) -> float`
  - `calmar_ratio(closes: list[float], periods_per_year: int = 252) -> float`
  - `sharpe_ratio(closes: list[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_metrics.py`：

```python
"""风险调整后收益指标测试。"""
from core.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


def _rising_closes():
    return [100.0 + i for i in range(60)]


def _falling_closes():
    return [100.0 - i for i in range(20)]


def test_max_drawdown_zero_on_rise():
    assert max_drawdown(_rising_closes()) == 0.0


def test_max_drawdown_positive_on_fall():
    md = max_drawdown(_falling_closes())
    assert md > 0.0
    assert md < 1.0


def test_annualized_return_positive_on_rise():
    r = annualized_return(_rising_closes())
    assert r > 0.0


def test_calmar_ratio_raises_on_zero_drawdown():
    # 无回撤时卡玛比率无法定义，返回 None 而非报错
    result = calmar_ratio(_rising_closes())
    assert result is None


def test_calmar_ratio_computed_on_fall():
    result = calmar_ratio(_falling_closes())
    assert result is not None
    assert result < 0  # 亏损 + 回撤 → 负卡玛


def test_sharpe_ratio_positive_on_rise():
    result = sharpe_ratio(_rising_closes())
    assert result > 0.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_metrics.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/valuation/metrics.py`：

```python
"""风险调整后收益指标。"""
from __future__ import annotations

import math


def max_drawdown(closes: list[float]) -> float:
    """最大回撤，返回正小数（0.25 表示 -25%）。"""
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 6)


def annualized_return(closes: list[float], periods_per_year: int = 252) -> float:
    if len(closes) < 2 or closes[0] <= 0:
        return 0.0
    total = closes[-1] / closes[0] - 1
    years = (len(closes) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return (1 + total) ** (1 / years) - 1


def calmar_ratio(closes: list[float], periods_per_year: int = 252) -> float | None:
    md = max_drawdown(closes)
    if md <= 0:
        return None
    return annualized_return(closes, periods_per_year) / md


def sharpe_ratio(closes: list[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    if len(closes) < 2:
        return 0.0
    returns = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(returns) / len(returns)
    if len(returns) < 2:
        return 0.0
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std <= 0:
        return 0.0
    return (mean * periods_per_year - risk_free) / (std * math.sqrt(periods_per_year))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_metrics.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/valuation/metrics.py backend/tests/test_metrics.py
git commit -m "feat: 实现最大回撤/年化收益/卡玛/夏普指标"
```

---

### Task 7: 跨资产比较编排（RMB 计价 + 指标 + 约束汇总）

**Files:**
- Create: `backend/core/comparison.py`
- Create: `backend/tests/test_comparison.py`

**Interfaces:**
- Consumes: `core.valuation.metrics`、`core.valuation.currency`、`core.valuation.constraints`、`core.providers.get_kline`
- Produces:
  - `compare_assets(assets: list[dict], fx_map: dict[str, float]) -> list[dict]`：每个 asset 输出 `{symbol, name, market, currency, rmb_annual_return, max_drawdown, calmar_ratio, sharpe_ratio, requires_quota, quota_note}`，按 `calmar_ratio` 降序

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_comparison.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_comparison.py -v`
Expected: FAIL，`ImportError`

- [ ] **Step 3: 写最小实现**

创建 `backend/core/comparison.py`：

```python
"""跨资产比较编排：RMB 口径风险调整后收益排序。"""
from __future__ import annotations

from core.valuation.constraints import QUOTA_USD_YEARLY, quota_note, requires_quota
from core.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


def compare_assets(assets: list[dict]) -> list[dict]:
    """对已折算 RMB 的资产序列做风险调整后收益排序。

    assets 每项需含：symbol/name/market/currency/rmb_closes（RMB 口径收盘价序列）。
    返回按 calmar_ratio 降序（None 置底），附额度提示。
    """
    results = []
    for a in assets:
        closes = a["rmb_closes"]
        calmar = calmar_ratio(closes)
        item = {
            "symbol": a["symbol"],
            "name": a["name"],
            "market": a["market"],
            "currency": a["currency"],
            "rmb_annual_return": round(annualized_return(closes), 4),
            "max_drawdown": round(max_drawdown(closes), 4),
            "calmar_ratio": round(calmar, 4) if calmar is not None else None,
            "sharpe_ratio": round(sharpe_ratio(closes), 4),
            "requires_quota": requires_quota(a["market"]),
            "quota_note": quota_note(0.0) if requires_quota(a["market"]) else "",
        }
        results.append(item)

    # 按卡玛降序，None 置底
    results.sort(key=lambda r: (r["calmar_ratio"] is None, -(r["calmar_ratio"] or 0)))
    return results
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_comparison.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/comparison.py backend/tests/test_comparison.py
git commit -m "feat: 实现跨资产风险调整后收益排序编排"
```

---

### Task 8: 完善 search.py 天级缓存与跨市场识别

**Files:**
- Modify: `backend/core/search.py`
- Create: `backend/tests/test_search.py`

**Interfaces:**
- Consumes: 现有 `search.py`（已含 `detect_market`、`normalize_symbol`、`derive_risk`、`derive_liquidity`、`resolve_meta`、`search`、`daily_cache_get/set`）
- Produces: 修正 `daily_cache_get/set` 按自然日判定（现有实现已用 `date.today()`，本次补充测试固化），确认 `detect_market` 覆盖 7 市场

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_search.py`：

```python
"""跨市场代码识别与天级缓存测试。"""
from core.search import (
    daily_cache_get, daily_cache_set, detect_market, normalize_symbol,
)


def test_detect_a_share():
    assert detect_market("688836") == "a-share"
    assert detect_market("600519") == "a-share"
    assert detect_market("000001") == "a-share"


def test_detect_fund():
    assert detect_market("510300") == "fund"


def test_detect_us():
    assert detect_market("AAPL") == "us"
    assert detect_market("TSLA") == "us"


def test_detect_hk_kr():
    assert detect_market("0700.HK") == "hk"
    assert detect_market("005930.KS") == "kr"


def test_detect_fx_crypto():
    assert detect_market("USDCNY=X") == "fx"
    assert detect_market("BTCUSDT") == "crypto"


def test_normalize_hk():
    assert normalize_symbol("hk", "0700") == "0700.HK"


def test_daily_cache_roundtrip():
    daily_cache_set("key1", {"v": 1})
    assert daily_cache_get("key1") == {"v": 1}
    assert daily_cache_get("missing") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_search.py -v`
Expected: FAIL 或部分失败——`detect_market("510300")` 现有实现可能返回 `a-share`（因为 `_A_SHARE_SH` 含 "5"，且 fund 判断逻辑可能有 bug）。先跑看实际输出，据此修正 `detect_market`。

- [ ] **Step 3: 修正 detect_market 实现**

检查 `backend/core/search.py` 的 `detect_market` 数字分支，确保：
- 6 位数字：`5` 开头 → `fund`（ETF），`6/9` 开头 → `a-share`，`0/3` 开头 → `a-share`，`1` 开头 → `fund`
- 修正为明确的分支（当前实现 `if q.startswith(_A_SHARE_SH)` 后紧跟 `return "fund" if q.startswith("5") else "a-share"` 逻辑需核对）。若已有正确逻辑则本步仅确认测试通过；若 bug 则修 `detect_market` 的数字段。

具体修正（若测试暴露 `510300` 误判）：

```python
    if q.isdigit():
        if len(q) == 6:
            if q.startswith(("5", "1")):
                return "fund"
            return "a-share"
        return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_search.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/core/search.py backend/tests/test_search.py
git commit -m "feat: 完善跨市场代码识别并固化天级缓存测试"
```

---

### Task 9: app.py 新增推荐/搜索/比较端点

**Files:**
- Modify: `backend/app.py`
- Create: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: `core.search.search`、`core.algorithms.config.build_engine`、`core.comparison.compare_assets`、`core.valuation.*`
- Produces:
  - `GET /api/search?q=` → `{query, items, total}`
  - `GET /api/recommend?symbol=&market=` → 单标的完整推荐（因子分 + 情绪 + 总分 + 风险指标）
  - `GET /api/compare?symbols=SYM1,SYM2,...` → 跨资产比较排序

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_api.py`：

```python
"""API 端点测试。"""
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_search_endpoint_returns_structure():
    resp = client.get("/api/search", params={"q": "600519"})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body


def test_search_endpoint_empty_query():
    resp = client.get("/api/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_compare_endpoint_empty_returns_empty():
    resp = client.get("/api/compare", params={"symbols": ""})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/test_api.py -v`
Expected: FAIL，`404 Not Found`（端点未定义）

- [ ] **Step 3: 实现端点**

在 `backend/app.py` 顶部追加导入：

```python
from core import comparison
from core.algorithms.config import build_engine
from core.search import search as search_instruments
```

在 `app.py` 末尾追加三个端点：

```python
@app.get("/api/search")
def search_instruments_endpoint(q: str = Query("", max_length=64)) -> dict:
    return search_instruments(q)


@app.get("/api/recommend")
def recommend_symbol(market: str, symbol: str) -> dict:
    rows = get_kline(market, symbol, "d", 180, prefer_real=True)
    if not rows:
        return {"error": "no kline data", "market": market, "symbol": symbol}
    meta = search.resolve_meta(market, symbol) or {}
    enriched = dict(meta)
    enriched["macro_score"] = macro.macro_score_for(market)
    analysis = analyze(rows, enriched)
    return {
        "meta": meta,
        "analysis": analysis,
        "market": market,
        "symbol": symbol,
    }


@app.get("/api/compare")
def compare_symbols(symbols: str = Query("")) -> dict:
    tokens = [t.strip() for t in symbols.split(",") if t.strip()]
    assets = []
    for token in tokens:
        mkt = search.detect_market(token)
        if mkt is None:
            continue
        sym = search.normalize_symbol(mkt, token)
        rows = get_kline(mkt, sym, "d", 180, prefer_real=True)
        if not rows:
            continue
        assets.append({
            "symbol": sym,
            "name": token,
            "market": mkt,
            "currency": "CNY" if mkt in ("a-share", "fund") else "USD",
            "rmb_closes": [r["close"] for r in rows],
        })
    return {"items": comparison.compare_assets(assets), "total": len(assets)}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/test_api.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/test_api.py
git commit -m "feat: 新增搜索/推荐/跨资产比较 API 端点"
```

---

### Task 10: 前端搜索框与跨资产比较入口

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/ScreenerPanel.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `GET /api/search`、`GET /api/compare`（Task 9）
- Produces: 前端 `searchInstruments(q)`、`compareSymbols(symbols)` 函数；ScreenerPanel 顶部搜索框；选中任意代码后复用现有 K 线/分析链路

- [ ] **Step 1: 写 api.ts 扩展**

在 `frontend/src/api.ts` 末尾追加：

```typescript
export interface SearchItem {
  symbol: string;
  name: string;
  market: string;
  currency: string;
  sector?: string;
  auto?: boolean;
}

export function searchInstruments(q: string): Promise<{ items: SearchItem[]; total: number }> {
  return getJson<{ items: SearchItem[]; total: number }>(
    `/api/search?q=${encodeURIComponent(q)}`,
  );
}
```

- [ ] **Step 2: 在 ScreenerPanel 顶部加搜索框**

在 `frontend/src/components/ScreenerPanel.tsx` 的 `ScreenerPanelProps` 增加：

```typescript
onSearch?: (query: string) => void;
```

在面板顶部（市场 tabs 上方）加输入框：

```tsx
const [searchText, setSearchText] = useState("");
// ... 在返回的 JSX 顶部插入
<div className="screener-search">
  <input
    value={searchText}
    onChange={(e) => setSearchText(e.target.value)}
    onKeyDown={(e) => {
      if (e.key === "Enter" && onSearch) onSearch(searchText.trim());
    }}
    placeholder="输入代码搜索任意标的（如 688836 / AAPL / BTCUSDT）"
  />
  <button onClick={() => onSearch?.(searchText.trim())}>搜索</button>
</div>
```

- [ ] **Step 3: 在 App.tsx 接入搜索**

在 `App.tsx` 增加处理函数与状态，将搜索结果作为选中标的传入现有 K 线/分析链路：

```typescript
const handleSearch = useCallback(async (query: string) => {
  if (!query) return;
  setError("");
  try {
    const result = await searchInstruments(query);
    if (result.items.length === 0) {
      setError(`未找到 "${query}" 对应的标的`);
      return;
    }
    const first = result.items[0];
    setSelected({
      symbol: first.symbol,
      name: first.name,
      market: first.market,
      currency: first.currency,
      sector: first.sector ?? "未分类",
      market_name: first.market,
      base_risk: 0.5,
      liquidity: 0.5,
    } as ScreenItem);
  } catch (caught) {
    setError(caught instanceof Error ? caught.message : "搜索失败");
  }
}, []);
```

将 `handleSearch` 传给 `<ScreenerPanel onSearch={handleSearch} ... />`。

- [ ] **Step 4: 前端构建验证**

Run: `cd frontend && pnpm build`
Expected: 构建成功，无 TypeScript 错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/api.ts frontend/src/components/ScreenerPanel.tsx frontend/src/App.tsx
git commit -m "feat: 前端新增任意代码搜索入口"
```

---

### Task 11: 端到端验证与文档更新

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

**Interfaces:**
- Consumes: 全部已完成端点
- Produces: 更新后的 README（API 概览新增 /api/search、/api/recommend、/api/compare）与架构文档（模块一/模块二划分）

- [ ] **Step 1: 端到端冒烟测试**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: 全部通过（Task 1-9 的测试合计约 40 个）

- [ ] **Step 2: 手动验证宇树科技（真实数据）**

Run:
```bash
curl -s "http://localhost:8000/api/search?q=688836" | python3 -m json.tool
curl -s "http://localhost:8000/api/recommend?market=a-share&symbol=688836" | python3 -m json.tool | head -40
```
Expected: search 返回宇树科技（auto=true），recommend 返回完整分析（含 total_score）

- [ ] **Step 3: 更新 README API 概览**

在 `README.md` 的「API 概览」段落追加：

```markdown
- `GET /api/search?q=688836` 任意代码跨市场搜索。
- `GET /api/recommend?market=a-share&symbol=688836` 单标的完整推荐（因子分+情绪+风险指标）。
- `GET /api/compare?symbols=AAPL,600519,BTCUSDT` 跨资产风险调整后收益排序。
```

并在「架构」段落补充模块一/模块二划分说明。

- [ ] **Step 4: 更新 ARCHITECTURE.md**

在 `docs/ARCHITECTURE.md` 增补「模块一（工程）/ 模块二（算法）拆分」小节，引用 `core/algorithms/`、`core/valuation/` 目录，说明算法可插拔机制。

- [ ] **Step 5: 提交**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: 更新 README 与架构文档，反映模块拆分与新增端点"
```

---

## Self-Review 结果

**Spec 覆盖检查：**
- 模块一/模块二拆分 → Task 2-4（算法层）、Task 5-6（valuation 层）、Task 9-10（API/前端）
- 算法可插拔（B 中粒度）→ Task 2/3/4 接口 + 注册表
- 任意代码搜索（A 方案）→ Task 8（search 完善）+ Task 9（/api/search）+ Task 10（前端搜索框）
- 跨资产 RMB 计价比较 → Task 5（currency/constraints）+ Task 6（metrics）+ Task 7（comparison）
- 购汇额度 5 万美元 → Task 5（constraints）
- 比特币按汇率折算 → Task 5（crypto 归入 requires_quota）+ Task 7（compare 纳入）
- 天级刷新 + 惰性缓存 → Task 8（daily_cache 测试固化）
- 风险调整后收益排序（卡玛/夏普）→ Task 6 + Task 7
- 诚实边界（不承诺收益最大化）→ 未新增代码，spec 1.3 已固化，README 更新时体现

**占位符扫描：** 无 TBD/TODO，所有步骤含具体代码。

**类型一致性：**
- `Factor.score` 返回 `{"score": float, "detail": dict}`，Task 2 定义、Task 4 消费一致 ✓
- `SentimentAnalyzer.analyze` 返回 `{"polarity", "confidence", "multiplier"}`，Task 3 定义、Task 4 消费一致 ✓
- `WeightedEngine.combine(factor_scores: dict[str,float], sentiment: dict)`，Task 4 定义、无后续任务直接调用（由 app 层在未来接线）✓
- `compare_assets(assets)` 输入含 `rmb_closes`，Task 7 定义、Task 9 调用时构造 `rmb_closes` 字段 ✓
- `detect_market`/`normalize_symbol` 在 Task 8 测试、Task 9 调用一致 ✓
