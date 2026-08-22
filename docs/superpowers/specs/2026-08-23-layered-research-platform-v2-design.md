# 全标的投研平台架构深化设计（v2）

> 日期：2026-08-23
> 状态：待评审
> 目标：在 2026-08-23 四层架构方案基础上，补齐端口定义、数据层语义、降级链路、应用层服务、展示层契约与迁移顺序，形成可实施的深化设计。

---

## 1. 背景与核心诉求

当前系统已经具备跨市场搜索、全市场候选发现、因子引擎与跨资产比较能力，但代码边界仍然混合：`app.py` 同时 import `providers`、`screener`、`macro`、`search`、`indicators` 与 `algorithms`，`screener.py` 直接调用 `providers.get_kline`，业务编排无法脱离真实网络测试。

本次深化设计必须满足三个核心诉求：

1. **数据仓库可独立优化**：应用层只依赖仓库端口，SQLite 的表结构、索引与 SQL 全部锁在基础设施层内部，后续换 DuckDB、Postgres 或优化查询不影响其他层。
2. **算法层可独立开发**：算法层只消费 `AnalysisContext` 和领域值对象，不 import 数据源、仓库、FastAPI，不发起网络请求，可独立测试和演进。
3. **前端界面可替换**：前端与后端之间以稳定的 `/api/*` 契约为界，展示层只负责参数校验和响应格式，不承载业务判断；替换前端不需要改动后端业务层。

## 2. 已确认约束

- 深化 2026-08-23 分层架构方案，不另起炉灶。
- API 契约基本不变，前端调用方式保持不变，后端内部渐进重构。
- SQLite 仓库与增量同步纳入本轮设计。
- 零新增第三方依赖：SQLite 使用 Python 标准库 `sqlite3`，仓库、缓存、同步手写轻量实现。
- 交付物为完整设计文档与实施计划。

## 3. 总体架构

采用依赖倒置的端口与适配器风格，依赖方向如下：

```text
presentation（FastAPI 路由 + schema）
    ↓ 调用
application（应用服务）
    ↓ 依赖 application/ports.py 中声明的端口
domain（纯值对象 + 指标 + 算法 + 估值）
    ↑ 实现
infrastructure（ProviderDataSource / SqliteRepository / 缓存 / 同步）
```

规则：

- 端口（`MarketDataRepository`、`MarketDataSource`、`FxRateProvider`）统一定义在 `application/ports.py`。
- `infrastructure/` 只负责实现端口，实现类可以自由优化内部细节。
- `domain/` 不 import `infrastructure`、`providers`、`sqlite`、`fastapi`，也不发起网络请求。
- `app.py` 是 composition root，负责组装仓库、数据源、同步器与各应用服务，再注入路由。
- `core/` 作为兼容层保留，设退出条件：所有路由迁移到 `presentation/` 且旧模块无人引用后删除。

### 3.1 目录结构

```text
backend/
├── app.py                       # composition root + FastAPI 实例
├── presentation/
│   ├── api/
│   │   ├── routes.py            # 路由只调应用服务
│   │   └── schemas.py           # 请求/响应契约（保持现有 API 兼容）
│   └── dependencies.py          # Depends 装配
├── application/
│   ├── ports.py                 # 数据仓库/数据源/汇率端口
│   ├── services/
│   │   ├── analysis_service.py
│   │   ├── screening_service.py
│   │   ├── recommendation_service.py
│   │   ├── comparison_service.py
│   │   └── sync_service.py
│   └── config.py                # 应用配置与装配策略
├── domain/
│   ├── models.py                # Instrument / KlineRow 等值对象
│   ├── indicators.py
│   ├── valuation/
│   └── algorithms/
├── infrastructure/
│   ├── datasources/
│   │   ├── provider_datasource.py
│   │   └── registry.py
│   ├── repository/
│   │   └── sqlite.py
│   ├── cache.py
│   └── sync.py
├── core/                        # 兼容层（限期保留）
└── tests/
    ├── unit/
    ├── integration/
    └── contracts/
```

## 4. 数据层设计

### 4.1 端口定义

端口统一定义在 `application/ports.py`：

```python
class MarketDataRepository(Protocol):
    def upsert_instruments(self, items: list[Instrument]) -> None: ...
    def upsert_klines(self, market: str, symbol: str, rows: list[KlineRow]) -> None: ...
    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None) -> list[KlineRow]: ...
    def get_watermark(self, market: str, symbol: str, period: str) -> str | None: ...
    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None: ...
    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None: ...
    def get_snapshot(self, date: str, market: str) -> list[dict]: ...
    def save_evaluation(self, evaluated_on: str, market: str, symbol: str,
                        score: float, payload: dict) -> None: ...
    def get_evaluation(self, evaluated_on: str, market: str, symbol: str) -> dict | None: ...
```

```python
class MarketDataSource(Protocol):
    def list_instruments(self, market: str, top_n: int) -> list[Instrument]: ...
    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None,
                   limit: int = 180) -> list[KlineRow]: ...
    def get_live_fx_rates(self) -> dict[str, float] | None: ...
```

```python
class FxRateProvider(Protocol):
    def reference_fx_rate(self, currency: str) -> float | None: ...
```

```python
class MacroNewsProvider(Protocol):
    def market_bias(self, market: str) -> dict | None: ...
    def macro_score(self, market: str) -> float: ...
    def news_items(self, market: str) -> list[dict]: ...
```

`ProviderDataSource` 同时实现 `MarketDataSource` 与 `FxRateProvider`；`MacroNewsProvider` 由现有 `macro.py` 数据适配为基础设施实现。

### 4.2 SQLite 实现要点

- 使用标准库 `sqlite3`，数据库文件默认为 `backend/data/research.db`，路径由 `application/config.py` 配置，测试注入临时路径。
- 沿用五张表：`instruments`、`klines`、`market_snapshots`、`evaluations`、`sync_watermarks`。
- `evaluations` 的语义明确为“同一天评估结果缓存”，替代现有 `search.py` 的 `daily_cache_get/set`；`payload` 存 JSON 结果，同键同天只算一次，跨天自然失效。
- `market_snapshots` 存每个自然日全市场候选池（按成交额/流动性前 N），推荐/筛选当天优先复用，缺当天数据才触发重新拉取。
- 常用查询建立索引：`klines(market, symbol, period, time)` 主键天然覆盖区间查询；`market_snapshots(date, market)` 加索引。
- 写入统一使用 `INSERT OR REPLACE`；连接使用 `check_same_thread=False` 加进程内写锁，兼容现有 `ThreadPoolExecutor` 并发筛选。

表结构：

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

CREATE INDEX idx_market_snapshots_date_market
  ON market_snapshots(date, market);

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

### 4.3 读取与降级链路

```text
应用服务
  → repository.get_klines
      ├─ 本地缺口为空 → 直接返回，source = "local"
      └─ 本地缺口非空
          → SyncService.sync(market, symbol, period, 缺口区间)
          → datasource.get_klines（沿用多源路由 + 5min 缓存 + 120s 熔断）
          → 成功 → repository.upsert_klines 写回、推进水位线 → 返回，source = "live"
          → 全部上游失败 → 确定性 mock 兜底 → 返回，source = "mock"
```

- 仓库读失败（如文件损坏）：捕获后回退数据源直读、不写回，保证接口仍可用。
- `source` 字段保持兼容：`live` / `mock` 语义不变，新增 `local` 表示当天已同步的本地数据，前端现有“实时/模拟”展示不受影响。
- 数据源失败在 `infrastructure` 内部走熔断和 mock 兜底，不向应用层泄漏 provider 细节。
- 应用服务不直接触达数据源，数据缺口统一由 `SyncService.sync` 补齐。

### 4.4 增量同步

`SyncService` 作为应用层用例编排，不包含业务规则：

```text
SyncService.sync(market, symbol, period, start=None, end=None)
  → repository.get_watermark
  → datasource.get_klines(market, symbol, period, start, end)
  → repository.upsert_klines
  → repository.set_watermark（写库成功才推进，失败不推进，下次重试）
```

- 同步触发时机：推荐、筛选、分析发现数据缺口时按需同步；不新增 API 端点，保持契约不变。
- 失败重试：水位线不推进，本次请求回退 mock；下一次请求自动重试，不引入定时任务。
- `SyncService` 测试注入内存仓库和假数据源，不触发网络。

## 5. 领域与算法层设计

领域层保持纯逻辑，只处理稳定的值对象与数据契约：

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

- `indicators.py` 保留纯函数指标：均线、MACD、RSI、布林、ATR、波动率。
- `algorithms/` 保留现有注册表与 `build_engine` 工厂，因子、情绪分析、推荐引擎继续可插拔，独立开发只发生在 `domain/algorithms/` 内部。
- `valuation/` 保持纯函数：RMB 计价、购汇额度约束、风险调整后指标；汇率由应用层通过 `FxRateProvider` 注入，`currency.py` 不再 import `providers`。

## 6. 应用层设计

五个服务，职责单一，全部通过构造函数注入依赖：

| 服务 | 职责 |
|---|---|
| `AnalysisService` | 单标的分析：读 K 线 → 缺口补齐 → 领域指标/引擎 → 结果 |
| `ScreeningService` | 筛选：候选池 → 并发评分 → 过滤排序 → 原因构建 |
| `RecommendationService` | 跨市场推荐：候选发现 → 并发评分 → 引擎合成 → evaluations 缓存 |
| `ComparisonService` | 跨资产比较：解析标的 → 读 K 线 → 注入汇率 → 领域估值/排序 |
| `SyncService` | 增量同步：水位线 → 拉缺口 → 写回 → 推进水位线 |

迁移规则：

- `screener.py` 的评分与推荐编排迁入 `ScreeningService` / `RecommendationService`，不再直接 import `providers`。
- `_build_reasons`、`_news_for_market` 这类“把分析结果翻译成推荐原因”的逻辑迁入应用层，通过注入的 `MacroNewsProvider` 取值，不再 import `macro` 常量。
- `comparison.py` 的编排逻辑迁入 `ComparisonService`，`valuation/` 保持纯函数。
- 推荐与筛选优先读仓库，缺数据时触发按需拉取并写回。

依赖注入示例：

```python
class RecommendationService:
    def __init__(self, repository: MarketDataRepository,
                 datasource: MarketDataSource,
                 engine: RecommendationEngine,
                 fx_provider: FxRateProvider,
                 macro_news: MacroNewsProvider,
                 sync_service: SyncService):
        ...
```

## 7. 展示层设计

`presentation/` 只做参数校验、调用应用服务、输出兼容响应三件事：

- `routes.py`：每个端点只调对应 service，业务判断为零。
- `schemas.py`：请求参数用 Pydantic Query/Model 校验（FastAPI 自带，不算新增依赖）；响应结构保持现有字段，`source`、`items`、`score` 等一律不破坏。
- `app.py`：收敛为 composition root，创建 `SqliteMarketDataRepository`、`ProviderDataSource`、`SyncService` 和五个服务，放入 `ServiceContainer`，注册路由，不再承载业务。
- `dependencies.py`：从 `ServiceContainer` 取服务并提供给路由，不在路由内实例化任何依赖。

前端不需要改调用方式；`frontend/src/types.ts` 继续与 API 手写同步，作为前后端契约。

## 8. 错误处理与降级

- `presentation`：参数错误由 FastAPI 返回 422；业务失败保持现有 `{"error": "..."}` 响应结构。
- `application`：抛出明确业务异常（如 `SymbolNotFound`、`NoKlineData`），由路由层转换为稳定错误响应；数据不足时由服务决定是否降级。
- `infrastructure`：数据源失败内部熔断 + mock 兜底；仓库读/写失败时捕获并降级为直读数据源，保证接口可用。
- 同步失败不推进水位线，下一次请求自动重试；`source` 统一为 `local` / `live` / `mock`。

## 9. 测试策略

```text
tests/unit/          领域层纯函数 + 应用服务（内存仓库、假数据源，零网络）
tests/unit/          基础设施仓库（临时 SQLite 文件，验证 upsert/水位线/快照）
tests/integration/   FastAPI TestClient + 临时数据库，跑现有全部端点
tests/contracts/     API 响应结构断言（source/items/score 等关键字段），锁住前后端契约
```

- 现有测试在 `core/` 兼容层存续期间继续保留并保持通过。
- 新增测试重点覆盖：仓库缺口补拉、水位线不推进、mock 兜底、`evaluations` 同日缓存、跨天失效。

## 10. 迁移顺序

```text
Phase 0  建立 domain/models.py 值对象，锁定测试基线
Phase 1  application/ports.py + infrastructure/repository/sqlite.py + cache + sync
Phase 2  ProviderDataSource 适配现有 providers 路由/熔断/兜底
Phase 3  应用服务逐个迁移：Analysis → Comparison → Screening → Recommendation
Phase 4  presentation/routes + dependencies 替换 app.py 路由，全量回归
Phase 5  无引用后删除 core/ 兼容层，更新 README 与 ARCHITECTURE
```

每阶段都可运行、可提交、API 不回归；提交信息按项目规范使用中文。

## 11. 非目标

- 不引入微服务、消息队列或分布式调度器。
- 不引入 ORM、Alembic、OpenAPI 类型生成等新依赖。
- 不重写现有算法实现，只锁定边界并补值对象。
- 不新增前端页面或 API 端点；API 契约保持兼容。
