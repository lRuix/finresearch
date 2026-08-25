# Backend 接入数仓 PostgreSQL 数据源设计

> 日期：2026-08-25
> 状态：待评审
> 范围：backend 数据访问层切换到数仓 PostgreSQL；同步服务下线；业务缓存落数仓

## 1. 目标与范围

### 1.1 目标

- 前端所有数据从数仓（PostgreSQL `warehouse` 库）读取，SQLite 退出 backend 数据链路（仅保留为数仓初始迁移来源）。
- backend 不再提供运行时行情同步：查询缺数据时直接返回已有数据，不自动补齐。
- 推荐评估缓存、市场快照缓存继续保留，落数仓新增应用表。

### 1.2 不做的事

- 不改动前端代码。
- 不改动数仓 ODS/DWD/DWS 分层表结构与 ETL 流程。
- 不实现 backend → 数仓的行情写入（`upsert_klines` 等同步方法下线）。
- 不接入外部数据源（SEC/CoinGecko 等由数仓 `sync_external` 维护）。

## 2. 架构

```text
前端 React SPA
  ↓ HTTP /api/*
FastAPI（presentation → application → domain）
  ↓ MarketDataRepository 端口
PostgresMarketDataRepository（数仓 warehouse 库）
  ├─ 读 fact_kline JOIN dim_instrument（行情）
  ├─ 读/写 backend_evaluations（推荐缓存）
  └─ 读/写 backend_market_snapshots（市场快照）
```

`SyncService` 从 `build_container` 装配中移除；`analysis` / `comparison` / `screening`
服务不再依赖同步，数据不足时返回已有数据。

## 3. 组件设计

### 3.1 `backend/infrastructure/repository/postgres.py`

`PostgresMarketDataRepository(dsn: str)`，实现 `application/ports.py` 的 `MarketDataRepository`：

| 方法 | 实现 |
|---|---|
| `get_klines` | `SELECT` `fact_kline` JOIN `dim_instrument`（market_id + symbol + period 归一化 + 时间范围），按时间升序返回 `KlineRow` |
| `get_evaluation` / `save_evaluation` | 读写 `backend_evaluations`（主键 `(evaluated_on, market, symbol)`，`payload` 为 JSONB） |
| `get_snapshot` / `upsert_snapshot` | 读写 `backend_market_snapshots`（主键 `(date, market, symbol)`，条目存 JSONB 数组/行） |
| `upsert_klines` / `upsert_instruments` / `get_watermark` / `set_watermark` | 抛 `NotImplementedError`（同步下线，生产无调用方） |

period 归一化：backend 与数仓均以 `d` 表示日线；`get_klines` 将请求 period 归一化到数仓 `fact_kline.period`。

### 3.2 装配切换

- `AppConfig` 增加 `warehouse_dsn: str | None = None`，默认读环境变量 `WAREHOUSE_DSN`。
- `build_container` 增加可选参数 `repository`；`warehouse_dsn` 存在时构造 `PostgresMarketDataRepository`，否则沿用 `SqliteMarketDataRepository`。
- `ServiceContainer.repository` 类型注解放宽为端口类型。

### 3.3 同步下线

- `build_container` 不再构造/注入 `SyncService`。
- `AnalysisService` / `ComparisonService` / `ScreeningService` 构造签名移除 `sync_service`，删除 `self._sync.sync(...)` 调用，数据不足直接使用已读数据。
- `backend/application/services/sync_service.py` 保留文件（不删除），但不再被装配引用。

## 4. 数仓新增应用表

新文件 `warehouse/models/05_backend_runtime.sql`（独立于分层表，`IF NOT EXISTS` 幂等）：

```sql
CREATE TABLE IF NOT EXISTS backend_evaluations (
  evaluated_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (evaluated_on, market, symbol)
);

CREATE TABLE IF NOT EXISTS backend_market_snapshots (
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  turnover DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  rank INTEGER NOT NULL,
  PRIMARY KEY (date, market, symbol)
);
```

## 5. 错误处理

- PG 连接失败：由 FastAPI 层自然返回 500；装配时 `warehouse_dsn` 不可达则启动报错（显式配置即要求可用）。
- 未实现的同步方法：抛 `NotImplementedError`，消息明确"同步服务已下线"。
- 数仓无对应标的/无行情：`get_klines` 返回空列表（缺数据就缺数据）。

## 6. 测试策略（TDD）

- `backend/tests/unit/test_postgres_repository.py`：连 `warehouse_test` 库验证
  - `get_klines` 读数仓装载的 K 线（先种数据，断言 OHLCV/时间范围/period 归一化）
  - `save_evaluation` / `get_evaluation` 幂等读写
  - `get_snapshot` / `upsert_snapshot` 读写
  - 同步方法抛 `NotImplementedError`
- 容器装配测试：`test_service_container` 适配两种模式（默认 SQLite；传 `warehouse_dsn` 用 PG 仓库）
- 服务改造回归：`analysis` / `screening` / `comparison` 现有单测更新（去掉 sync 依赖），行为改为"无数据返回空"
- backend 全量测试回归（SQLite 路径不受影响）

## 7. 运行与文档

- README / ARCHITECTURE 更新：backend 数据源为数仓 PostgreSQL；`WAREHOUSE_DSN` 启用说明。
