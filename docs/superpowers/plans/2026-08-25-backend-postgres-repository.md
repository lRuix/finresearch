# Backend 接入数仓 PostgreSQL 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** backend 数据访问层切换到数仓 PostgreSQL：前端所有数据从数仓读取，同步服务下线，业务缓存（评估/快照）落数仓应用表。

**Architecture:** 新增 `PostgresMarketDataRepository`（读 `fact_kline`，读写 `backend_evaluations` / `backend_market_snapshots`）；`AppConfig.warehouse_dsn` 存在时装配 PG 仓库；`AnalysisService` / `ComparisonService` / `ScreeningService` 移除 `SyncService` 依赖，数据不足返回已有数据。

**Tech Stack:** Python 3.12、FastAPI、psycopg 3、PostgreSQL 16（数仓）。

**Spec:** `docs/superpowers/specs/2026-08-25-backend-postgres-repository-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `warehouse/models/05_backend_runtime.sql` | 新增 `backend_evaluations` / `backend_market_snapshots` |
| `backend/infrastructure/repository/postgres.py` | `PostgresMarketDataRepository` |
| `backend/application/config.py` | `AppConfig.warehouse_dsn` |
| `backend/app.py` | 装配切换 + 移除 SyncService |
| `backend/application/services/analysis_service.py` | 移除 sync 依赖 |
| `backend/application/services/comparison_service.py` | 移除 sync 依赖 |
| `backend/application/services/screening_service.py` | 移除 sync 依赖 |
| `backend/tests/unit/test_postgres_repository.py` | PG 仓库测试 |
| `backend/tests/integration/test_service_container.py` | 两种装配模式适配 |
| `backend/tests/unit/test_analysis_service.py` 等 | 服务单测适配 |

---

### Task 1: 数仓应用表 DDL

**Files:**
- Create: `warehouse/models/05_backend_runtime.sql`

- [ ] **Step 1: 创建 `warehouse/models/05_backend_runtime.sql`**

```sql
-- backend 业务运行数据（应用缓存，不参与数仓 ODS/DWD/DWS 分层）
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

- [ ] **Step 2: 在 `warehouse` 与 `warehouse_test` 两个库执行 DDL**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && for db in warehouse warehouse_test; do docker exec -i warehouse-db-1 psql -U warehouse -d $db -v ON_ERROR_STOP=1 -q -f - < models/05_backend_runtime.sql; done`
Expected: 两个库均无报错；`\dt` 可见 `backend_evaluations`、`backend_market_snapshots`。

- [ ] **Step 3: Commit**

```bash
git add warehouse/models/05_backend_runtime.sql
git commit -m "feat: 数仓新增 backend 业务运行应用表"
```

---

### Task 2: PostgresMarketDataRepository（TDD）

**Files:**
- Create: `backend/infrastructure/repository/postgres.py`
- Test: `backend/tests/unit/test_postgres_repository.py`

- [ ] **Step 1: 准备 backend 测试环境**

Run: `python3 -m venv /Users/hxjs1/Documents/project/finresearch/backend/.venv && /Users/hxjs1/Documents/project/finresearch/backend/.venv/bin/pip install -q fastapi "psycopg[binary]" pytest httpx`
Expected: 安装完成；`.venv/bin/python -c "import fastapi, psycopg, httpx"` 无报错。

- [ ] **Step 2: 写失败测试 `backend/tests/unit/test_postgres_repository.py`**

```python
"""PostgreSQL repository tests against the warehouse_test database."""
from __future__ import annotations

import json

import psycopg
import pytest
from psycopg.types.json import Jsonb

from domain.models import Instrument, KlineRow
from infrastructure.repository.postgres import PostgresMarketDataRepository


DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test"
SYMBOL = "TEST-PG-600519"


@pytest.fixture
def repo():
    return PostgresMarketDataRepository(DSN)


@pytest.fixture
def seed_kline():
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dim_market (market_id, name, region, currency) VALUES ('a-share', 'A-Share', 'CN', 'CNY') ON CONFLICT DO NOTHING"
        )
        cur.execute(
            """
            INSERT INTO dim_instrument (market_id, symbol, name)
            VALUES ('a-share', %s, 'TEST')
            ON CONFLICT (market_id, symbol) DO NOTHING
            RETURNING instrument_id
            """,
            (SYMBOL,),
        )
        row = cur.fetchone()
        instrument_id = row[0] if row else None
        if instrument_id is None:
            cur.execute(
                "SELECT instrument_id FROM dim_instrument WHERE market_id='a-share' AND symbol=%s",
                (SYMBOL,),
            )
            instrument_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO fact_kline (
              market_id, instrument_id, provider_id, date_key, period,
              time, open, high, low, close, volume
            ) VALUES
              ('a-share', %s, 'backend', '2026-08-01', 'd',
               '2026-08-01T00:00:00+00:00', 10, 11, 9, 10.5, 100),
              ('a-share', %s, 'backend', '2026-08-02', 'd',
               '2026-08-02T00:00:00+00:00', 10.5, 12, 10, 11.5, 120)
            ON CONFLICT (market_id, instrument_id, period, time) DO UPDATE SET
              open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
              close = EXCLUDED.close, volume = EXCLUDED.volume
            """,
            (instrument_id, instrument_id),
        )
        conn.commit()

    yield
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM fact_kline WHERE provider_id = 'backend'
              AND instrument_id IN (
                SELECT instrument_id FROM dim_instrument WHERE symbol = %s)
            """,
            (SYMBOL,),
        )
        cur.execute("DELETE FROM dim_instrument WHERE symbol = %s", (SYMBOL,))
        cur.execute("DELETE FROM backend_evaluations WHERE symbol LIKE 'TEST-PG-%'")
        cur.execute("DELETE FROM backend_market_snapshots WHERE symbol LIKE 'TEST-PG-%'")
        conn.commit()


def test_get_klines_reads_fact_kline(repo, seed_kline):
    rows = repo.get_klines("a-share", SYMBOL, "d")
    assert len(rows) == 2
    assert rows[0].time == "2026-08-01T00:00:00+00:00"
    assert rows[0].open == 10
    assert rows[0].close == 10.5
    assert rows[1].close == 11.5
    assert [row.time for row in rows] == sorted(row.time for row in rows)


def test_get_klines_filters_by_time_range(repo, seed_kline):
    rows = repo.get_klines("a-share", SYMBOL, "d", start="2026-08-02")
    assert len(rows) == 1
    assert rows[0].time == "2026-08-02T00:00:00+00:00"


def test_get_klines_empty_when_missing(repo, seed_kline):
    assert repo.get_klines("a-share", "TEST-PG-NOPE", "d") == []


def test_save_and_get_evaluation(repo, seed_kline):
    repo.save_evaluation("2026-08-25", "all", "TEST-PG-EVAL", 88.5, {"k": "v"})
    result = repo.get_evaluation("2026-08-25", "all", "TEST-PG-EVAL")
    assert result == {"k": "v"}
    repo.save_evaluation("2026-08-25", "all", "TEST-PG-EVAL", 90.0, {"k": "v2"})
    assert repo.get_evaluation("2026-08-25", "all", "TEST-PG-EVAL") == {"k": "v2"}


def test_upsert_and_get_snapshot(repo, seed_kline):
    items = [
        {"symbol": "TEST-PG-SNAP", "name": "S", "turnover": 1.0, "market_cap": 2.0, "rank": 1},
        {"symbol": "TEST-PG-SNAP2", "name": "S2", "turnover": 3.0, "market_cap": 4.0, "rank": 2},
    ]
    repo.upsert_snapshot("2026-08-25", "a-share", items)
    snap = repo.get_snapshot("2026-08-25", "a-share")
    assert len(snap) == 2
    assert snap[0]["rank"] <= snap[1]["rank"]


def test_sync_methods_raise_not_implemented(repo):
    with pytest.raises(NotImplementedError):
        repo.upsert_klines("a-share", "X", "d", [KlineRow("2026-08-01", 1, 2, 0.5, 1.5, 10)])
    with pytest.raises(NotImplementedError):
        repo.upsert_instruments([Instrument(market="a-share", symbol="X", name="X", currency="CNY")])
    with pytest.raises(NotImplementedError):
        repo.set_watermark("a-share", "X", "d", "2026-08-01")
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd /Users/hxjs1/Documents/project/finresearch/backend && .venv/bin/python -m pytest tests/unit/test_postgres_repository.py -q`（需要 escalation 连 127.0.0.1:5432）
Expected: `ModuleNotFoundError: No module named 'infrastructure.repository.postgres'`

- [ ] **Step 4: 实现 `backend/infrastructure/repository/postgres.py`**

```python
"""PostgreSQL implementation of MarketDataRepository backed by the warehouse."""
from __future__ import annotations

import json
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from domain.models import Instrument, KlineRow


_PERIOD_ALIASES = {"1d": "d", "d": "d", "day": "d", "1h": "h", "1w": "w", "w": "w"}


class PostgresMarketDataRepository:
    """Read market data from the warehouse; sync writes are not supported."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn)

    def _normalize_period(self, period: str) -> str:
        return _PERIOD_ALIASES.get(str(period).lower(), str(period))

    def get_klines(
        self,
        market: str,
        symbol: str,
        period: str,
        start: str | None = None,
        end: str | None = None,
    ) -> list[KlineRow]:
        sql = """
            SELECT f.time, f.open, f.high, f.low, f.close, f.volume
            FROM fact_kline f
            JOIN dim_instrument i ON i.instrument_id = f.instrument_id
            WHERE i.market_id = %s AND i.symbol = %s AND f.period = %s
        """
        params: list[Any] = [market, symbol, self._normalize_period(period)]
        if start is not None:
            sql += " AND f.time >= %s"
            params.append(start)
        if end is not None:
            sql += " AND f.time <= %s"
            params.append(end)
        sql += " ORDER BY f.time ASC"
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            KlineRow(
                time=row["time"].isoformat(),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
            for row in rows
        ]

    def save_evaluation(
        self, evaluated_on: str, market: str, symbol: str, score: float, payload: dict
    ) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO backend_evaluations (evaluated_on, market, symbol, score, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (evaluated_on, market, symbol) DO UPDATE SET
                  score = EXCLUDED.score, payload = EXCLUDED.payload,
                  updated_at = now()
                """,
                (evaluated_on, market, symbol, score, Jsonb(payload)),
            )
            conn.commit()

    def get_evaluation(
        self, evaluated_on: str, market: str, symbol: str
    ) -> dict | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM backend_evaluations WHERE evaluated_on=%s AND market=%s AND symbol=%s",
                (evaluated_on, market, symbol),
            )
            row = cur.fetchone()
        return dict(row[0]) if row else None

    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO backend_market_snapshots (date, market, symbol, name, turnover, market_cap, rank)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, market, symbol) DO UPDATE SET
                  name = EXCLUDED.name, turnover = EXCLUDED.turnover,
                  market_cap = EXCLUDED.market_cap, rank = EXCLUDED.rank
                """,
                [
                    (
                        date,
                        market,
                        item["symbol"],
                        item.get("name", ""),
                        item.get("turnover"),
                        item.get("market_cap"),
                        item["rank"],
                    )
                    for item in items
                ],
            )
            conn.commit()

    def get_snapshot(self, date: str, market: str) -> list[dict]:
        with self._connect() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT symbol, name, turnover, market_cap, rank
                FROM backend_market_snapshots
                WHERE date = %s AND market = %s
                ORDER BY rank ASC
                """,
                (date, market),
            )
            return [dict(row) for row in cur.fetchall()]

    def upsert_klines(self, market: str, symbol: str, period: str, rows: list[KlineRow]) -> None:
        raise NotImplementedError("行情同步服务已下线：数据由数仓 ETL 维护")

    def upsert_instruments(self, items: list[Instrument]) -> None:
        raise NotImplementedError("标的写入已下线：由数仓 ETL 维护 dim_instrument")

    def get_watermark(self, market: str, symbol: str, period: str) -> str | None:
        raise NotImplementedError("行情同步服务已下线：不维护同步水位线")

    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None:
        raise NotImplementedError("行情同步服务已下线：不维护同步水位线")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/backend && .venv/bin/python -m pytest tests/unit/test_postgres_repository.py -q`（escalation）
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/infrastructure/repository/postgres.py backend/tests/unit/test_postgres_repository.py
git commit -m "feat: backend PostgreSQL 仓库实现（读数仓、缓存落库、同步下线）"
```

---

### Task 3: 装配切换

**Files:**
- Modify: `backend/application/config.py`
- Modify: `backend/app.py`
- Modify: `backend/tests/integration/test_service_container.py`

- [ ] **Step 1: `config.py` 增加 `warehouse_dsn`**

```python
from dataclasses import dataclass
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "research.db"


def _warehouse_dsn() -> str | None:
    return os.environ.get("WAREHOUSE_DSN") or None


@dataclass(frozen=True)
class AppConfig:
    db_path: Path = DEFAULT_DB_PATH
    warehouse_dsn: str | None = None
    cache_ttl_seconds: int = 300
    breaker_seconds: int = 120

    def __post_init__(self) -> None:
        if self.warehouse_dsn is None:
            object.__setattr__(self, "warehouse_dsn", _warehouse_dsn())
```

- [ ] **Step 2: `app.py` 装配切换并移除 SyncService**

在 `app.py` 修改：

```python
from application.ports import MarketDataRepository, MarketDataSource
from infrastructure.repository.postgres import PostgresMarketDataRepository
from infrastructure.repository.sqlite import SqliteMarketDataRepository
```

`ServiceContainer` 中 `repository: SqliteMarketDataRepository` 改为 `repository: MarketDataRepository`；移除 `sync_service: SyncService` 字段。

`build_container` 改为：

```python
def build_container(
    config: AppConfig | None = None,
    datasource: MarketDataSource | None = None,
    repository: MarketDataRepository | None = None,
) -> ServiceContainer:
    config = config or AppConfig()
    if repository is None:
        repository = (
            PostgresMarketDataRepository(config.warehouse_dsn)
            if config.warehouse_dsn
            else SqliteMarketDataRepository(config.db_path)
        )
    datasource = datasource or ProviderDataSource()
    macro_news = MacroNewsProvider()
    symbol_resolver = SymbolResolver(datasource)
    catalog = CatalogService()
    screening = ScreeningService(repository, macro_news, datasource)
    recommendation = RecommendationService(repository, screening)
    comparison = ComparisonService(repository, symbol_resolver, datasource)
    analysis = AnalysisService(
        repository, symbol_resolver, macro_news, datasource,
    )
    search_service = SearchService(datasource)
    macro_service = MacroService(macro_news)
    return ServiceContainer(
        config=config, repository=repository, datasource=datasource,
        macro_news=macro_news, symbol_resolver=symbol_resolver,
        catalog_service=catalog, screening_service=screening,
        recommendation_service=recommendation,
        comparison_service=comparison, analysis_service=analysis,
        search_service=search_service, macro_service=macro_service,
    )
```

（移除 `sync_service = SyncService(...)` 与容器字段；`SyncService` import 一并移除。）

- [ ] **Step 3: 更新 `test_service_container.py`**

默认模式断言不变（`isinstance(container.repository, SqliteMarketDataRepository)`）；新增：

```python
def test_container_uses_postgres_repository_when_dsn_set(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_DSN", "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test")
    container = build_container()
    assert isinstance(container.repository, PostgresMarketDataRepository)
```

- [ ] **Step 4: 跑容器测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/backend && .venv/bin/python -m pytest tests/integration/test_service_container.py -q`
Expected: 全部通过（先修 Task 4 的服务签名会导致失败，因此本步先跑并记录，待 Task 4 完成后全绿）

- [ ] **Step 5: Commit**

```bash
git add backend/application/config.py backend/app.py backend/tests/integration/test_service_container.py
git commit -m "feat: backend 装配支持数仓 PostgreSQL 仓库切换"
```

---

### Task 4: 同步服务下线（服务改造）

**Files:**
- Modify: `backend/application/services/analysis_service.py`
- Modify: `backend/application/services/comparison_service.py`
- Modify: `backend/application/services/screening_service.py`
- Modify: `backend/tests/unit/test_analysis_service.py`、`test_comparison_service.py`、`test_screening_service.py`

- [ ] **Step 1: `analysis_service.py` 移除 sync**

构造签名删除 `sync_service: SyncService` 与 `self._sync = sync_service`；删除三处 `self._sync.sync(...)` 调用（第 37、68、76 行附近），数据不足路径改为直接使用已读 `rows`。同步 import `from application.services.sync_service import SyncService` 一并删除。

- [ ] **Step 2: `comparison_service.py` 移除 sync**

构造签名删除 `sync_service` 与 `self._sync`；删除第 34 行 `self._sync.sync(market, symbol, "d")`，直接读 `get_klines`。

- [ ] **Step 3: `screening_service.py` 移除 sync**

构造签名删除 `sync_service` 与 `self._sync`；删除第 47 行 `self._sync.sync(...)`。

- [ ] **Step 4: 更新三个服务单测**

把 `AnalysisService(repository, sync_service=..., ...)` 等构造调用改为新签名（删除 sync 参数），断言"无数据时返回空/已有数据"。

- [ ] **Step 5: 全量测试回归**

Run: `cd /Users/hxjs1/Documents/project/finresearch/backend && .venv/bin/python -m pytest tests -q`（escalation）
Expected: 全部通过（含 Task 3 容器测试）。

- [ ] **Step 6: Commit**

```bash
git add backend/application/services/ backend/tests/unit/
git commit -m "refactor: backend 移除运行时行情同步服务"
```

---

### Task 5: 文档与端到端验证

- [ ] **Step 1: 更新 `README.md` / `docs/ARCHITECTURE.md`**

说明 backend 数据源为数仓 PostgreSQL：设置 `WAREHOUSE_DSN` 即启用；行情由数仓 ETL 每日维护，backend 不再运行时同步；推荐缓存落 `backend_evaluations`。

- [ ] **Step 2: 端到端启动验证**

Run: `cd /Users/hxjs1/Documents/project/finresearch/backend && WAREHOUSE_DSN=postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse .venv/bin/python -m uvicorn app:app --port 8000`（后台启动）

随后 `curl http://127.0.0.1:8000/api/analyze?market=a-share&symbol=600519`（escalation），Expected: 返回基于数仓 K 线的分析结果（`total_klines > 0`）。

- [ ] **Step 3: Commit**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: 同步 backend 数仓数据源说明"
```
