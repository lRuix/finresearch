# 全球投研终端 v2 — 跨市场标的推荐系统设计

> 日期：2026-08-21
> 状态：待评审
> 目标：将「固定候选池 MVP」升级为「任意代码可搜索 + 跨资产风险调整后排序推荐」的研究终端。

---

## 1. 背景与目标

### 1.1 现状问题

当前项目（`finresearch`）是一个 Web MVP，存在以下限制：

1. **标的池硬编码**：`backend/core/universe.py` 固定 30 个标的，`find_symbol()` 只查这张表，任意代码（如宇树科技 688836）无法分析。
2. **评分依赖人工字段**：`base_risk`、`liquidity` 需人工评估，放开任意代码后绝大多数标的不具备这两个值。
3. **无跨币种计价**：A 股（CNY）、美股（USD）、韩股（KRW）、加密（USDT）的收益直接混比，未折算回统一本币，跨资产比较失真。
4. **无约束模型**：未考虑购汇额度（每人每年等值 5 万美元）、汇率变动对收益的影响。
5. **无风险调整后收益口径**：只有 0-100 综合评分，没有「最大回撤 / 卡玛比率 / 夏普比率」等普通用户可理解的跨资产比较指标。
6. **算法与工程耦合**：评分逻辑全部堆在 `indicators.py` / `screener.py` 大函数里，无法替换单个因子或算法。

### 1.2 目标（已与用户确认）

| # | 决策点 | 结论 |
|---|---|---|
| 1 | 架构拆分 | 模块一（工程化落地）+ 模块二（算法设计与落地），算法可插拔替换 |
| 2 | 算法粒度 | B 中粒度：推荐引擎 / 因子 / 情绪分析三层接口 |
| 3 | 天级评估 | 惰性天级缓存（按自然日缓存），不引入调度器 |
| 4 | 任意代码搜索 | A 方案：任意代码可查（跨市场识别 + 数据源探测） |
| 5 | 跨资产比较 | 统一 RMB 计价 + 风险调整后收益排序 |
| 6 | 汇率/额度 | 汇率折算入收益；购汇额度每人每年等值 5 万美元硬约束 |
| 7 | 比特币 | 纳入评估，按 USDT→USD→RMB 折算，不做合规限制 |
| 8 | 投资周期 | 股票天级、基金 1-2 年、外汇/加密按默认表（可配置） |

### 1.3 诚实的边界（重要）

本系统输出的是**风险调整后的相对排序与配置建议**，**不是**「收益最大化」或「确定性收益预测」。原因（金融学共识）：

- 未来收益不可观测，只能估计分布，且估计误差巨大。
- 均值-方差优化对输入误差极敏感（「误差最大化器」陷阱）。
- 跨资产比较必须统一计价、统一时间窗、并显式标注不确定性。

因此系统的诚实定位是：**「给定风险预算、投资期限与购汇约束下，输出跨资产的相对风险调整后评分与配置建议，并标注不确定性」。**

---

## 2. 总体架构：模块一 / 模块二

```
backend/
├── core/
│   ├── providers.py          # [模块一] 数据获取：多源路由 + 缓存 + 熔断
│   ├── search.py             # [模块一] 跨市场代码识别 + 任意标的解析
│   ├── valuation/            # [模块一] 计价与约束层（新增）
│   │   ├── currency.py       #   统一 RMB 计价：收益(RMB) = 收益(本币) + 汇率变动
│   │   └── constraints.py    #   硬约束：购汇额度 5w USD/年、资产类别期限
│   ├── algorithms/           # [模块二] 算法层（可插拔，新增）
│   │   ├── context.py        #   AnalysisContext：工程层传给算法的干净数据契约
│   │   ├── engines/          #   推荐引擎（合成方式）
│   │   │   ├── base.py       #     RecommendationEngine 接口
│   │   │   └── weighted.py   #     因子加权合成（默认实现）
│   │   ├── factors/          #   因子（打分器）
│   │   │   ├── base.py       #     Factor 接口
│   │   │   ├── trend.py      #     趋势因子
│   │   │   ├── momentum.py   #     动量因子
│   │   │   ├── volatility.py #     低波动因子
│   │   │   ├── risk.py       #     风险因子
│   │   │   └── macro.py      #     宏观因子
│   │   └── sentiment/        #   情绪分析
│   │       ├── base.py       #     SentimentAnalyzer 接口
│   │       └── news_rule.py  #     新闻情绪规则（默认实现）
│   ├── screener.py           # [模块一] 筛选编排（调用算法层，不感知具体实现）
│   └── indicators.py         # [模块二] 指标计算（保留，供因子复用）
└── app.py                    # [模块一] FastAPI 端点
```

### 2.1 模块一（工程化，稳定不随算法变）

- **数据获取**：`providers.py` 保持现状（多源路由 + 5min 缓存 + 熔断），是稳定的数据管道。
- **搜索解析**：`search.py` 跨市场代码识别 + 任意标的探测。
- **计价与约束层（新增）**：`valuation/` 负责统一 RMB 计价和硬约束校验。
- **API / 前端**：端点与界面，只依赖抽象接口。

### 2.2 模块二（算法，可插拔替换）

- **指标计算**：`indicators.py` 保留为纯函数工具库，被因子调用。
- **因子**：每个因子独立实现 `Factor` 接口，可增删替换。
- **情绪分析**：`SentimentAnalyzer` 接口，默认新闻规则实现，可换 FinBERT/VADER 等。
- **推荐引擎**：`RecommendationEngine` 接口，默认加权合成实现。

### 2.3 替换机制：注册表 + 配置

算法实现通过注册表登记，配置指定启用哪个：

```python
# 配置（settings / 环境变量）
ALGORITHM_CONFIG = {
    "engine": "weighted",
    "factors": ["trend", "momentum", "volatility", "risk", "macro"],
    "sentiment": "news_rule",
    "weights": {"trend": 0.30, "momentum": 0.25, "volatility": 0.15,
                "risk": 0.15, "macro": 0.15},
}
```

工程层只调用 `engine.combine(...)`，不感知具体算法。换算法 = 改配置 + 新增实现文件。

---

## 3. 数据契约：AnalysisContext

工程层把「干净数据」打包成上下文传给算法层，算法层不直接碰数据源：

```python
@dataclass
class AnalysisContext:
    symbol: str
    market: str                 # a-share / fund / us / kr / hk / fx / crypto
    currency: str               # 本币
    klines: list[dict]          # K 线（已按资产类别取合适窗口）
    macro_bias: float           # 市场宏观偏置分 0-100
    news_sentiment: float       # 新闻情绪原始分 -1..1
    fx_rate: float | None       # 本币→RMB 汇率（跨币种折算用）
    horizon: str                # 投资周期档位：daily / short / medium / long
```

设计原则：算法层不 import `providers`，不发起网络请求，只消费 `AnalysisContext`。这保证算法可单测、可替换。

---

## 4. 计价与约束层（模块一）

### 4.1 统一 RMB 计价

跨资产比较前，所有收益折算回人民币：

```
收益(RMB) = 收益(本币) × (1 + 汇率变动率)
```

- 汇率源：项目已有外汇数据源（`frankfurter_klines` 的 `USDCNY=X` 等）。
- 跨币种折算汇率：USD、KRW、HKD、USDT → 先折算到 USD，再 USD→RMB。
- 只有单一币种（A 股、基金）时不折算，汇率因子 = 1。

### 4.2 硬约束：购汇额度

- 个人便利化购汇额度：每人每年**等值 5 万美元**（约 35 万人民币）。
- 需购汇的资产：美股、韩股、港股、外汇、数字货币。
- 约束校验：推荐结果按「占用购汇额度」累计，超出额度时标记或降权，并提示用户。

### 4.3 投资周期（可配置默认值）

| 资产类别 | 评价窗口（默认） | 周期档位 |
|---|---|---|
| 股票（A股/美股/韩股/港股） | 日频，20-60 交易日 | daily/short |
| 基金 | 1-2 年 | medium/long |
| 外汇 | 日频，60-120 交易日 | short |
| 数字货币 | 日频，30-90 交易日 | short |

周期影响两点：① 取多长历史窗口算收益/风险；② 持有期约束（短期资金不推需长持的基金）。

---

## 5. 算法设计（模块二）

### 5.1 三个接口契约

```python
# Factor 接口
class Factor(ABC):
    @property
    def name(self) -> str: ...
    def score(self, ctx: AnalysisContext) -> FactorResult:
        """输出 {score: 0-100, detail: {...}}"""

# SentimentAnalyzer 接口
class SentimentAnalyzer(ABC):
    def analyze(self, ctx: AnalysisContext) -> SentimentResult:
        """输出 {polarity: -1..1, confidence, multiplier: 0.8..1.2}"""

# RecommendationEngine 接口
class RecommendationEngine(ABC):
    @property
    def factors(self) -> list[Factor]: ...
    @property
    def sentiment(self) -> SentimentAnalyzer: ...
    def combine(self, factor_scores, sentiment) -> dict:
        """输出 {total_score, detail}"""
```

### 5.2 五个因子（沿用现有逻辑，拆为独立实现）

| 因子 | 打分逻辑 | 输出 |
|---|---|---|
| 趋势 Trend | 均线多头排列计数（5 项各 20 分） | 0-100 |
| 动量 Momentum | RSI 位置基准分 + 20 日涨跌修正 | 0-100 |
| 低波动 Volatility | 年化波动率 vs 市场目标分档 | 0-100 |
| 风险 Risk | (1 - 风险系数)×100，风险系数由波动率反推 | 0-100 |
| 宏观 Macro | 市场偏置分 | 0-100 |

### 5.3 情绪分析（乘数放大器）

```
情绪乘数 = 1 + 0.2 × polarity
```

- `polarity` ∈ [-1, +1]，来自市场新闻平均 sentiment。
- 极空 0.8 / 中性 1.0 / 极多 1.2。
- 替换点：未来可换 NLP 模型，只需实现接口。

### 5.4 合成公式（RecommendationEngine）

```
1. 因子原始分 → 同市场截面 z-score 标准化 → z_i
2. 合成 = Σ(z_i × w_i)          （w_i 可配置，默认见 ALGORITHM_CONFIG）
3. 合成分映射回 0-100
4. 最终评分 = 合成分 × 情绪乘数  （clamp 0-100）
```

**截面标准化范围**：同市场内（A 股自己比、加密自己比），不跨资产做 z-score——跨资产比较由「风险调整后收益」维度承担（见第 6 节）。

---

## 6. 跨资产比较：风险调整后收益排序

这是「钱放哪最好」的直接答案。除 0-100 评分外，新增**风险调整后收益指标**：

### 6.1 指标

| 指标 | 公式 | 用途 |
|---|---|---|
| 年化收益 | 几何年化 | 收益水平 |
| 年化波动率 | 标准差 × √252 | 风险水平 |
| 最大回撤 | 峰值到谷底最大跌幅 | 普通人最关心的风险 |
| **卡玛比率** | 年化收益 ÷ 最大回撤 | 排序主指标 |
| 夏普比率 | 超额收益 ÷ 波动率 | 排序次指标 |

### 6.2 跨资产排序流程

```
1. 各标的收益序列 → 折算 RMB（valuation.currency）
2. 按资产类别取合适评价窗口（valuation 周期表）
3. 算卡玛/夏普比率 → 跨资产可比分数
4. 叠加约束：购汇额度、合规（比特币不做限制）
5. 输出排序：同一 RMB 口径、同时窗下的风险调整后收益排行
```

### 6.3 输出形式（诚实标注）

每个推荐标的输出：

```
{
  symbol, name, market, currency,
  rmb_annual_return,      # RMB 口径年化收益
  max_drawdown,           # 最大回撤
  calmar_ratio,           # 卡玛比率
  score_0_100,            # 因子综合评分（0-100）
  auto: true/false,       # 是否自动推导（无人工元数据）
  fx_note,                # 汇率影响说明
  quota_note,             # 购汇额度说明（如需购汇）
}
```

---

## 7. 天级评估：惰性缓存

- 不引入调度器。
- 每个标的按「自然日」缓存评估结果：同日重复查询复用，跨天自动重算。
- 实现：`search.py` 已含 `daily_cache_get/set`（按 `date.today()` 判定）。

---

## 8. 数据流

```
用户查询（代码/关键词）
  → search.py 跨市场识别 + 探测
  → providers.py 取 K 线 + 汇率
  → valuation/currency.py 折算 RMB
  → algorithms/ 因子打分 + 情绪 + 合成（截面 z-score）
  → valuation/constraints.py 校验购汇额度
  → 输出：0-100 评分 + 风险调整后收益 + 约束提示
```

---

## 9. 错误处理与降级

| 场景 | 处理 |
|---|---|
| 数据源全失败 | 回退模拟数据（现有机制），标注 `source: mock` |
| 汇率源失败 | 用最近一次缓存汇率；无缓存则标注「汇率未知，收益为估算」 |
| 标的无人工元数据 | 自动推导 risk/liquidity，标注 `auto: true` |
| 因子数据不足（K 线太短） | 该因子跳过，合成分按可用因子归一化 |
| 超出购汇额度 | 结果标注 `quota_note`，不硬性剔除（提示用户） |

---

## 10. 测试策略

| 层 | 测试 |
|---|---|
| search.py | 跨市场代码识别（688836→a-share、AAPL→us、BTCUSDT→crypto、USDCNY=X→fx） |
| valuation | RMB 折算正确性、汇率变动计入、额度累计 |
| factors | 每个因子独立单测（给定 K 线，验证输出 0-100） |
| engine | 合成公式、截面 z-score、情绪乘数 |
| 端到端 | 宇树科技、特斯拉、基金、外汇、比特币的完整推荐链路 |

---

## 11. 不做的事（YAGNI）

- ❌ 不引入后台定时任务（惰性天级缓存足够）
- ❌ 不做全市场名录数据源（任意「代码」可查，不做「名称→代码」发现）
- ❌ 不做 ML/NLP 情绪模型（保留接口，默认新闻规则）
- ❌ 不承诺「收益最大化」或「确定性收益预测」（见 1.3 诚实边界）
- ❌ 不做实时逐笔/高频交易信号（天级已是上限）

---

## 12. 实施顺序建议

1. `valuation/`（计价 + 约束）—— 跨资产比较的根基
2. `algorithms/` 接口 + 因子拆分 —— 算法可插拔
3. `search.py` 完善 + 天级缓存 —— 任意代码搜索
4. `app.py` 新端点 + 前端搜索框 —— 用户入口
5. 测试 + 文档

（详细实施计划将由 writing-plans 技能生成，不在本 spec 展开）
