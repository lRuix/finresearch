# 独立 OLAP 数据仓库实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有仓库内新增独立 `warehouse/` 子项目，用纯 PostgreSQL 构建 ODS/DWD/DWS 分层数仓，先落数据采集、建模和装载。

**Architecture:** PostgreSQL 16 单实例，`warehouse/etl/` 负责采集与装载，`warehouse/models/` 保存 DDL，维度/事实表做星型模型，事实表按时间分区，DWS 用物化视图。

**Tech Stack:** PostgreSQL 16 + Docker Compose + Python 3.11 + psycopg + pytest。

---

## 执行前置检查

- [ ] `docker --version` 可用，`docker compose version` 可用。
- [ ] 主工作区 venv 已有 `psycopg`；如未安装，先安装 `psycopg[binary]`。
- [ ] 本任务只修改 `warehouse/` 与新增文档，不修改 `backend/`、`frontend/`。

## 文件结构

```text
warehouse/
├── docker-compose.yml
├── requirements.txt
├── README.md
├── models/
│   ├── 01_dim.sql
│   ├── 02_ods.sql
│   ├── 03_dwd.sql
│   └── 04_dws.sql
├── etl/
│   ├── __init__.py
│   ├── db.py
│   ├── providers.py
│   ├── load_ods.py
│   ├── build_dwd.py
│   └── build_dws.py
└── tests/
    ├── conftest.py
    ├── test_providers.py
    ├── test_load_ods.py
    ├── test_build_dwd.py
    └── test_build_dws.py
```

---

## Task 1: 项目脚手架与数据库连接

**Files:**
- Create: `warehouse/docker-compose.yml`
- Create: `warehouse/requirements.txt`
- Create: `warehouse/etl/__init__.py`
- Create: `warehouse/etl/db.py`
- Test: `warehouse/tests/conftest.py`

- [ ] **Step 1: 写 Docker Compose 与依赖**

`warehouse/docker-compose.yml`:

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: warehouse
      POSTGRES_PASSWORD: warehouse
      POSTGRES_DB: warehouse
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

`warehouse/requirements.txt`:

```text
psycopg[binary]>=3.1
pytest>=8.0
```

- [ ] **Step 2: 写测试共享夹具**

`warehouse/tests/conftest.py`:

```python
"""Shared fixtures and import path setup."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture(scope="session")
def dsn():
    return "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_providers.py -q`
Expected: 文件不存在，收集失败。

- [ ] **Step 4: 实现连接模块**

`warehouse/etl/db.py`:

```python
"""PostgreSQL connection helpers."""
from __future__ import annotations

from contextlib import contextmanager

import psycopg


@contextmanager
def connect(dsn: str):
    with psycopg.connect(dsn) as conn:
        yield conn


def execute_sql(dsn: str, sql: str) -> None:
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
```

- [ ] **Step 5: 提交**

```bash
git add warehouse/docker-compose.yml warehouse/requirements.txt warehouse/etl/__init__.py warehouse/etl/db.py warehouse/tests/conftest.py
git commit -m "feat: 初始化数仓项目脚手架与连接模块"
```

---

## Task 2: DDL 与维度表

**Files:**
- Create: `warehouse/models/01_dim.sql`
- Create: `warehouse/models/02_ods.sql`
- Create: `warehouse/models/03_dwd.sql`
- Create: `warehouse/models/04_dws.sql`

- [ ] **Step 1: 写维度表 DDL**

`warehouse/models/01_dim.sql`:

```sql
CREATE TABLE IF NOT EXISTS dim_date (
  date_key DATE PRIMARY KEY,
  year SMALLINT NOT NULL,
  month SMALLINT NOT NULL,
  day SMALLINT NOT NULL,
  is_trading_day BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_market (
  market_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT NOT NULL,
  currency TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_instrument (
  instrument_id BIGSERIAL PRIMARY KEY,
  market_id TEXT NOT NULL REFERENCES dim_market(market_id),
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  sector TEXT,
  UNIQUE (market_id, symbol)
);

CREATE TABLE IF NOT EXISTS dim_provider (
  provider_id TEXT PRIMARY KEY,
  name TEXT NOT NULL
);
```

- [ ] **Step 2: 写 ODS 表 DDL**

`warehouse/models/02_ods.sql` 先创建两个示例市场表，其余市场按 spec 第 5 节补齐：

```sql
CREATE TABLE IF NOT EXISTS ods_klines_a_share (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL, volume REAL,
  amount REAL, change_pct REAL, turnover_rate REAL, amplitude REAL,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);

CREATE TABLE IF NOT EXISTS ods_klines_fund (
  provider TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  interval TEXT NOT NULL,
  ts TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL, volume REAL,
  nav REAL, accum_nav REAL, daily_growth_pct REAL,
  purchase_status TEXT, redeem_status TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  UNIQUE (provider, market, symbol, interval, ts)
);
```

- [ ] **Step 3: 写 DWD 事实表 DDL**

`warehouse/models/03_dwd.sql`:

```sql
CREATE TABLE IF NOT EXISTS fact_kline (
  market_id TEXT NOT NULL,
  instrument_id BIGINT NOT NULL,
  provider_id TEXT NOT NULL,
  date_key DATE NOT NULL,
  period TEXT NOT NULL,
  time TIMESTAMPTZ NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL NOT NULL,
  PRIMARY KEY (market_id, instrument_id, period, time)
) PARTITION BY RANGE (time);

CREATE TABLE IF NOT EXISTS fact_news (
  news_id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL,
  sentiment REAL,
  tags JSONB NOT NULL DEFAULT '[]',
  UNIQUE (source, published_at, title)
);
```

- [ ] **Step 4: 写 DWS 物化视图 DDL**

`warehouse/models/04_dws.sql`:

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS dws_instrument_daily AS
SELECT market_id, instrument_id, date_key,
       count(*) AS rows_count,
       (max(close) - min(close)) / NULLIF(min(close), 0) AS amplitude,
       max(close) AS last_close,
       sum(volume) AS total_volume
FROM fact_kline
WHERE period = 'd'
GROUP BY market_id, instrument_id, date_key;

CREATE MATERIALIZED VIEW IF NOT EXISTS dws_market_daily AS
SELECT market_id, date_key,
       avg((close - open) / NULLIF(open, 0)) AS avg_daily_return,
       sum(volume) AS total_volume,
       count(DISTINCT instrument_id) AS instrument_count
FROM fact_kline
WHERE period = 'd'
GROUP BY market_id, date_key;
```

- [ ] **Step 5: 执行 DDL 并提交**

Run: `docker compose up -d db`
然后逐文件执行 DDL。
Commit:

```bash
git add warehouse/models
git commit -m "feat: 新增数仓维度、ODS、DWD 与 DWS DDL"
```

---

## Task 3: 数据源采集层

**Files:**
- Create: `warehouse/etl/providers.py`
- Test: `warehouse/tests/test_providers.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_providers.py`:

```python
"""Provider parsing tests."""
from etl.providers import parse_binance_klines, parse_gate_klines, parse_eastmoney_fund


def test_parse_binance_klines():
    raw = [[
        1787356800000, "78338.03", "78828.15", "76500.00",
        "77074.93", "18524.50", 1787443199999, "1433768388.59",
        3950045, "9413.19", "728650560.29", "0",
    ]]
    rows = parse_binance_klines(raw)
    assert rows[0]["quote_volume"] == 1433768388.59
    assert rows[0]["trades_count"] == 3950045


def test_parse_gate_klines():
    raw = [["1787356800", "808872838.726", "77078", "78835.1", "76500", "78336", "10439.731", "true"]]
    rows = parse_gate_klines(raw)
    assert rows[0]["quote_volume"] == 808872838.726
    assert rows[0]["volume"] == 10439.731


def test_parse_eastmoney_fund():
    item = {
        "FSRQ": "2026-08-21", "DWJZ": "2.8960", "LJJZ": "2.8960",
        "JZZZL": "-1.33", "SGZT": "开放申购", "SHZT": "开放赎回",
    }
    row = parse_eastmoney_fund(item)
    assert row["nav"] == 2.8960
    assert row["daily_growth_pct"] == -1.33
```

- [ ] **Step 2: 运行确认失败**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_providers.py -q`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 实现采集解析函数**

`warehouse/etl/providers.py` 实现 `parse_binance_klines`、`parse_gate_klines`、`parse_eastmoney_fund`，字段按本轮实测来源解析。

- [ ] **Step 4: 运行确认通过**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_providers.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/providers.py warehouse/tests/test_providers.py
git commit -m "feat: 新增各市场数据源字段解析"
```

---

## Task 4: ODS 装载

**Files:**
- Create: `warehouse/etl/load_ods.py`
- Test: `warehouse/tests/test_load_ods.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_load_ods.py` 插入 A 股与加密各一条，验证同键 upsert 后不重复：

```python
"""ODS loading tests."""
from etl.load_ods import upsert_ods_rows
from etl.db import connect


def test_upsert_is_idempotent(dsn):
    rows = [
        {
            "provider": "tencent", "market": "a-share", "symbol": "600519",
            "interval": "d", "ts": "2026-08-21", "open": 1, "high": 2,
            "low": 0.5, "close": 1.5, "volume": 100, "raw_payload": {},
            "sync_batch_id": "batch-1",
        }
    ]
    upsert_ods_rows(dsn, "a-share", rows)
    upsert_ods_rows(dsn, "a-share", rows)
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ods_klines_a_share")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_load_ods.py -q`
Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `load_ods`**

按 `market` 路由到对应 `ods_klines_*` 表，用 `INSERT ... ON CONFLICT ... DO UPDATE`，整批在同一事务提交。

- [ ] **Step 4: 运行确认通过**

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/load_ods.py warehouse/tests/test_load_ods.py
git commit -m "feat: 实现 ODS 贴源装载与幂等 upsert"
```

---

## Task 5: DWD 标准化装载

**Files:**
- Create: `warehouse/etl/build_dwd.py`
- Test: `warehouse/tests/test_build_dwd.py`

- [ ] **Step 1: 写失败测试**

测试从 ODS 抽取 A 股、外汇、场外基金，验证统一映射：外汇 `volume=0`、场外基金 `open=high=low=close=nav`、时间统一到交易日。

- [ ] **Step 2: 运行确认失败**

Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `build_dwd`**

先加载 `dim_market`、`dim_instrument`、`dim_provider`、`dim_date`，再从 ODS 按市场映射写入 `fact_kline`。

- [ ] **Step 4: 运行确认通过**

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/build_dwd.py warehouse/tests/test_build_dwd.py
git commit -m "feat: 实现 ODS 到 DWD 标准化装载"
```

---

## Task 6: DWS 聚合刷新

**Files:**
- Create: `warehouse/etl/build_dws.py`
- Test: `warehouse/tests/test_build_dws.py`

- [ ] **Step 1: 写失败测试**

测试刷新 `dws_market_daily` 后能查到聚合结果。

- [ ] **Step 2: 运行确认失败**

Expected: `ModuleNotFoundError`。

- [ ] **Step 3: 实现 `build_dws`**

按依赖顺序执行 `REFRESH MATERIALIZED VIEW dws_instrument_daily` 和 `dws_market_daily`。

- [ ] **Step 4: 运行确认通过**

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/build_dws.py warehouse/tests/test_build_dws.py
git commit -m "feat: 实现 DWS 物化视图刷新"
```

---

## Task 7: 初始迁移与新闻装载

**Files:**
- Create: `warehouse/etl/migrate_seed.py`
- Modify: `warehouse/README.md`

- [ ] **Step 1: 从现有 SQLite 抽取 K 线**

读取 `backend/data/research.db` 的 `klines`，按 `market` 路由写入 ODS，再走 DWD 装载。

- [ ] **Step 2: 新闻装载**

从 `backend/infrastructure/datasources/macro_data.py` 的 `NEWS_ITEMS` 与 RSS 抽取，写入 `ods_news` 和 `fact_news`。

- [ ] **Step 3: 执行端到端验证**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m etl.migrate_seed`
Expected: ODS、DWD、DWS 均有数据。

- [ ] **Step 4: 提交**

```bash
git add warehouse/etl/migrate_seed.py warehouse/README.md
git commit -m "feat: 实现初始迁移与新闻装载"
```

---

## 完成标准

- [ ] `docker compose up -d db` 成功。
- [ ] `warehouse/tests/` 全部 PASS。
- [ ] `fact_kline`、`fact_news`、`dws_*` 有数据。
- [ ] `backend/`、`frontend/` 未被修改。
