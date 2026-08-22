# 全标的投研平台架构设计

> 日期：2026-08-23
> 状态：待评审
> 目标：将当前投研终端重构为数据层、算法层、展示层清晰分离，同时具备模块化与可扩展能力的全标的投研平台。

---

## 1. 背景与现状问题

当前系统已经具备跨市场搜索、全市场候选发现、因子引擎与跨资产比较能力，但代码边界仍然混合，主要体现在：

1. 展示层直接依赖具体模块：`app.py` 同时 import `providers`、`screener`、`macro`、`search`、`indicators` 与 `algorithms`，前端逻辑和后端实现没有通过稳定的应用接口隔离。
2. 数据获取与业务编排耦合：`screener.py` 直接调用 `providers.get_kline`，应用逻辑无法脱离真实网络运行，导致单元测试必须依赖 mock 或外部网络。
3. 数据层缺少仓库抽象：`providers.py` 只用进程内缓存，没有持久化仓库，无法表达“先查本地、再拉上游、写回本地”的语义。
4. 领域层仍有外部依赖：`valuation/currency.py` 直接 import `providers` 拿实时汇率，破坏算法层的纯逻辑边界。
5. 数据模型不统一：`dict` 在 providers、search、screener、algorithms 之间传递，字段契约分散，扩展时容易破坏调用方。

## 2. 设计目标与非目标

### 2.1 目标

- 数据层、算法层、展示层物理分离，各自只依赖约定的接口。
- 数据源、本地存储、因子、引擎、前端展示均可替换或扩展。
- 算法层不 import 数据源、不发起网络请求，可以用纯内存数据单测。
- 数据层支持“外部数据源 + SQLite 本地库”两级读取和增量同步。
- 展示层通过应用服务使用业务能力，不直接理解 provider、SQL 或因子实现。

### 2.2 非目标

- 不引入微服务、消息队列或分布式调度器，单机投研平台用模块边界即可。
- 不把每一种数据源做成插件注册系统，只保留 `DataSource` 接口和轻量路由。
- 不一次性重写全部现有代码，采用兼容现有 API 的渐进迁移。

## 3. 总体架构

采用“端口与适配器”风格的模块化单体，四层依赖方向严格向下：

```text
Presentation 展示层
    ↓ 调用接口
Application 应用编排层
    ↓ 依赖端口与领域模型
Domain/Algorithm 算法与领域层
    ↓ 只依赖纯值对象
Infrastructure 数据与外部适配层
```

依赖规则：

- 展示层只能 import 应用层接口，不直接 import providers、screener、repository 或数据库实现。
- 应用层依赖领域层和端口接口，负责把数据、算法、约束编排成用例。
- 领域/算法层只依赖自身的数据契约和纯值对象，不 import 数据源、数据库、HTTP。
- 基础设施层实现端口接口，并由应用层在运行时注入。

### 3.1 目录结构

```text
backend/
├── app.py                       # FastAPI 实例与路由注册
├── presentation/               # 展示层：HTTP 适配器与响应契约
│   ├── api/
│   │   ├── routes.py
│   │   └── schemas.py
│   └── dependencies.py
├── application/                # 应用编排层：用例服务
│   ├── services/
│   │   ├── analysis_service.py
│   │   ├── screening_service.py
│   │   ├── recommendation_service.py
│   │   ├── comparison_service.py
│   │   └── sync_service.py
│   ├── contracts.py
│   └── config.py
├── domain/                     # 算法与领域层：纯逻辑
│   ├── models.py
│   ├── indicators.py
│   ├── valuation/
│   │   ├── currency.py
│   │   ├── constraints.py
│   │   └── metrics.py
│   └── algorithms/
│       ├── context.py
│       ├── factors/
│       ├── sentiment/
│       ├── engines/
│       └── config.py
├── infrastructure/             # 数据层：数据源、仓库、缓存与同步
│   ├── datasources/
│   │   ├── contracts.py
│   │   ├── provider_datasource.py
│   │   └── registry.py
│   ├── repository/
│   │   ├── contracts.py
│   │   └── sqlite.py
│   ├── cache.py
│   └── sync.py
├── core/                       # 兼容层：保留旧导入，逐步迁移
└── tests/
    ├── unit/
    ├── integration/
    └── contracts/
```

## 4. 数据层设计

数据层解决三个问题：外部数据从哪来、数据如何持久化、增量如何同步。它通过端口向应用层暴露能力，应用层不知道数据来自腾讯、yfinance、SQLite 还是 mock。

### 4.1 数据源端口

```python
class MarketDataSource(Protocol):
    def list_instruments(self, market: str, top_n: int) -> list[Instrument]: ...
    def get_klines(self, market: str, symbol: str, period: str,
                   limit: int) -> list[KlineRow]: ...
    def get_live_fx_rates(self) -> dict[str, float] | None: ...
```

`ProviderDataSource` 保留现有的多市场路由、失败熔断和模拟数据兜底逻辑，但不再同时承担持久化职责。每个市场可以有独立 provider 函数，未来新增数据源只需实现同一接口。

### 4.2 仓库端口

```python
class MarketDataRepository(Protocol):
    def upsert_instruments(self, items: list[Instrument]) -> None: ...
    def upsert_klines(self, market: str, symbol: str,
                      rows: list[KlineRow]) -> None: ...
    def get_klines(self, market: str, symbol: str,
                   start: str | None, end: str | None) -> list[KlineRow]: ...
    def get_watermark(self, market: str, symbol: str,
                      period: str) -> str | None: ...
    def set_watermark(self, market: str, symbol: str,
                      period: str, as_of: str) -> None: ...
```

`SqliteMarketDataRepository` 是首个实现。SQLite 零运维、单文件，足够支撑当前单用户投研场景；未来数据量上来后再替换成 DuckDB 或 Postgres，不影响应用层。

### 4.3 SQLite 表结构

```sql
CREATE TABLE instruments (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  currency TEXT NOT NULL,
  sector TEXT,
  base_risk REAL,
  liquidity REAL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, symbol)
);

CREATE TABLE klines (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  period TEXT NOT NULL,
  time TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  PRIMARY KEY (market, symbol, period, time)
);

CREATE TABLE market_snapshots (
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  turnover REAL,
  market_cap REAL,
  rank INTEGER NOT NULL,
  PRIMARY KEY (date, market, symbol)
);

CREATE TABLE evaluations (
  evaluated_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  score REAL NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (evaluated_on, market, symbol)
);

CREATE TABLE sync_watermarks (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  period TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY (market, symbol, period)
);
```

### 4.4 增量同步

`SyncService` 的职责是让“今天只需要更新今天的数据”：

1. 读 `sync_watermarks`，确定每个标的上次同步到哪一天。
2. 只向 `MarketDataSource` 请求缺口区间。
3. 通过仓库 `upsert_klines` 写入本地。
4. 只有写库成功后才推进水位线，失败不推进，下次自动重试。
5. 推荐和筛选优先读仓库，缺数据时再触发按需拉取。

## 5. 算法层设计

算法层是纯领域层，只处理稳定的值对象与数据契约，不感知外部世界。现有 `algorithms/` 已经基本满足这个要求，本方案主要是补上统一的领域模型和去掉 `valuation/currency.py` 对 providers 的依赖。

### 5.1 值对象

```python
@dataclass(frozen=True)
class Instrument:
    market: str
    symbol: str
    name: str
    currency: str
    sector: str | None = None
    base_risk: float | None = None
    liquidity: float | None = None

@dataclass(frozen=True)
class KlineRow:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
```

`AnalysisContext` 继续作为算法层入口，可以由值对象组装，也可以兼容旧 dict 转换。

### 5.2 算法模块

- `indicators.py`：纯函数指标，均线、MACD、RSI、布林、ATR、波动率。
- `algorithms/factors/`：因子接口与实现，继续使用注册表。
- `algorithms/sentiment/`：情绪分析接口与新闻规则实现。
- `algorithms/engines/`：推荐引擎接口、加权引擎与截面评分。
- `valuation/`：RMB 计价、风险指标、购汇约束，全部为纯函数，汇率由应用层传入。

算法层禁止 import `infrastructure`、`providers`、`sqlite`、`fastapi` 与任何网络模块。

## 6. 展示层设计

展示层包括 FastAPI 和 React，只负责输入校验、响应格式和界面渲染，不包含业务判断。

### 6.1 FastAPI 路由

```python
@router.get("/api/recommendations")
def recommendations(params: RecommendationQuery,
                    service: RecommendationService = Depends(...)):
    return service.get_recommendations(params)
```

路由只调应用服务，响应通过 Pydantic schema 输出。市场、周期、筛选条件等参数由 schema 统一校验。

### 6.2 前端边界

React 继续通过 `frontend/src/api.ts` 访问 API，不直接 import 后端实现。`types.ts` 与后端 Pydantic schema 保持同步，后续可以用 OpenAPI 自动生成类型，减少手工维护。

## 7. 应用层设计

应用层是数据层、算法层和展示层之间的编排层，承担当前 `screener.py` 和 `app.py` 里的业务组合逻辑。

核心服务：

- `AnalysisService`：单标的指标与分析。
- `ScreeningService`：按条件筛选与评分。
- `RecommendationService`：跨市场推荐与配额分配。
- `ComparisonService`：跨资产 RMB 口径比较。
- `SyncService`：数据增量同步与水位线维护。

服务依赖通过构造函数注入：

```python
class RecommendationService:
    def __init__(self, repository: MarketDataRepository,
                 datasource: MarketDataSource,
                 engine: RecommendationEngine,
                 fx_provider: FxRateProvider):
        ...
```

这样测试推荐逻辑时，可以注入内存仓库和固定数据源，不触发网络请求。

## 8. 关键数据流

### 8.1 首页推荐

```text
React → GET /api/recommendations
      → RecommendationService
      → repository 读取本地候选与 K 线
      → 缺失时 datasource 拉取并写回 repository
      → domain.algorithms 因子与引擎评分
      → valuation 统一计价与约束
      → presentation schema 输出
```

### 8.2 增量同步

```text
SyncService
  → repository.get_watermark
  → datasource 拉取缺口数据
  → repository.upsert_klines
  → repository.set_watermark
```

### 8.3 任意代码分析

```text
React → GET /api/analyze?market=us&symbol=GOOG
      → AnalysisService
      → repository 查本地 K 线
      → 本地缺失则 datasource 拉取并落库
      → domain.indicators 计算
      → 返回分析结果
```

## 9. 依赖注入与配置

使用 FastAPI 的 `Depends` 组装依赖，避免在服务里手写全局单例。

```python
def get_repository() -> MarketDataRepository:
    return SqliteMarketDataRepository(DB_PATH)

def get_datasource() -> MarketDataSource:
    return ProviderDataSource(settings)

def get_engine() -> RecommendationEngine:
    return build_engine(ALGORITHM_CONFIG)
```

配置集中在 `application/config.py` 与环境变量：

```text
DATABASE_PATH=data/finresearch.db
PROVIDER_TIMEOUT_SECONDS=6
CANDIDATES_PER_MARKET=20
```

## 10. 迁移路径

不一次性重写，按依赖方向从下往上迁移：

1. 先把 `providers` 收敛成 `MarketDataSource` 适配器，保留原函数作为默认 provider。
2. 新增 `SqliteMarketDataRepository` 和 K 线/水位线同步，验证增量拉取与落库。
3. 抽出应用服务，把 `screener.py`、`app.py` 的业务编排迁过去，旧 API 暂时兼容。
4. 把 `valuation/currency.py` 的汇率依赖改为应用层注入，清理领域层外部依赖。
5. 引入 Pydantic schema，收拢 API 响应，前端类型逐步对齐。
6. 删除兼容层中的旧路径，统一为新包结构。

每个阶段都保持现有测试可运行，新增测试覆盖该层的端口契约。

## 11. 测试策略

- 单元测试：算法层纯函数、因子、引擎、估值与约束，不 mock 网络。
- 契约测试：数据源与仓库实现满足端口接口。
- 集成测试：SQLite 仓库、增量同步、应用服务端到端链路。
- API 测试：展示层路由只验证参数、响应格式与服务编排。
- 前端测试：组件只依赖 API 类型和 mock 响应。

## 12. 不做的事

- 不引入统一事件总线或 CQRS，当前规模不需要。
- 不把因子、数据源做成热加载插件，文件级模块和注册表已足够。
- 不在第一阶段做复杂回测引擎，先落推荐结果表，回测作为后续迭代。
