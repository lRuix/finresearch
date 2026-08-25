# 数仓外部数据源接入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 warehouse 数仓接入 SEC EDGAR、CoinGecko、World Bank、akshare 四类外部数据源，构建 ODS 贴源 → DWD 通用指标 → DWS 日频的完整链路，支持每日增量同步。

**Architecture:** 每个数据源一个解析模块（`etl/sources/*.py`），统一输出贴源 dict；新增通用外部 ODS upsert（`etl/load_external.py`）与指标模型构建（`etl/build_indicator.py`）；`etl/sync_external.py` 按源独立事务装载并推进 `etl_watermarks` 水位线。

**Tech Stack:** Python 3.11+、psycopg 3、akshare（仅 A股源）、标准库 urllib（其余源）。

**Spec:** `docs/superpowers/specs/2026-08-25-external-data-sources-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `warehouse/models/02_ods.sql` | 新增 6 张外部 ODS 表（追加，幂等） |
| `warehouse/models/03_dwd.sql` | 新增 `dim_indicator` / `fact_indicator`（追加，幂等） |
| `warehouse/models/04_dws.sql` | 新增 `dws_indicator_daily` 物化视图（追加，幂等） |
| `warehouse/etl/load_external.py` | 外部 ODS 表元数据 + 通用 upsert |
| `warehouse/etl/sources/__init__.py` | sources 包标记 |
| `warehouse/etl/sources/sec_edgar.py` | SEC submissions/facts 抓取与解析 |
| `warehouse/etl/sources/coingecko.py` | CoinGecko 行情/市值抓取与解析 |
| `warehouse/etl/sources/worldbank.py` | World Bank 指标抓取与解析 |
| `warehouse/etl/sources/akshare_cn.py` | akshare 财务摘要/龙虎榜抓取与解析 |
| `warehouse/etl/build_indicator.py` | ODS → dim_indicator/fact_indicator 构建 |
| `warehouse/etl/sync_external.py` | 外部数据每日增量入口 |
| `warehouse/tests/test_load_external.py` | 通用 upsert 测试 |
| `warehouse/tests/test_sources_sec.py` 等 4 个 | 解析函数测试 |
| `warehouse/tests/test_build_indicator.py` | 指标模型构建测试 |
| `warehouse/tests/test_sync_external.py` | 增量/回滚/水位线测试 |
| `warehouse/requirements.txt` | 增加 `akshare>=1.18` |
| `warehouse/README.md` | 每日运行说明 |

---

### Task 1: DDL 建表

**Files:**
- Modify: `warehouse/models/02_ods.sql`
- Modify: `warehouse/models/03_dwd.sql`
- Modify: `warehouse/models/04_dws.sql`

- [ ] **Step 1: 在 `models/02_ods.sql` 末尾追加外部 ODS 表**

```sql
-- ============ 外部数据源 ODS ============
CREATE TABLE IF NOT EXISTS ods_sec_submissions (
  cik TEXT NOT NULL,
  ticker TEXT,
  company_name TEXT NOT NULL,
  exchange TEXT,
  sic TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (cik)
);

CREATE TABLE IF NOT EXISTS ods_sec_facts (
  cik TEXT NOT NULL,
  concept TEXT NOT NULL,
  unit TEXT NOT NULL,
  period_end DATE NOT NULL,
  value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (cik, concept, unit, period_end)
);

CREATE TABLE IF NOT EXISTS ods_crypto_meta (
  coin_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  snapshot_date DATE NOT NULL,
  current_price DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  total_volume DOUBLE PRECISION,
  high_24h DOUBLE PRECISION,
  low_24h DOUBLE PRECISION,
  market_cap_rank INTEGER,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (coin_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS ods_macro_indicators (
  country_code TEXT NOT NULL,
  indicator_code TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  date TEXT NOT NULL,
  value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (country_code, indicator_code, date)
);

CREATE TABLE IF NOT EXISTS ods_cn_financials (
  symbol TEXT NOT NULL,
  report_date TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  indicator_value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, report_date, indicator_name)
);

CREATE TABLE IF NOT EXISTS ods_cn_lhb (
  trade_date TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  close_price DOUBLE PRECISION,
  change_pct DOUBLE PRECISION,
  reason TEXT NOT NULL DEFAULT '',
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (trade_date, code, reason)
);
```

- [ ] **Step 2: 在 `models/03_dwd.sql` 末尾追加指标模型**

```sql
CREATE TABLE IF NOT EXISTS dim_indicator (
  indicator_id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  source_key TEXT NOT NULL,
  name TEXT NOT NULL,
  unit TEXT,
  frequency TEXT,
  UNIQUE (source, source_key)
);

CREATE TABLE IF NOT EXISTS fact_indicator (
  indicator_id BIGINT NOT NULL REFERENCES dim_indicator(indicator_id),
  ref_key TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  value DOUBLE PRECISION,
  extra JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (indicator_id, ref_key, as_of_date)
);
```

- [ ] **Step 3: 在 `models/04_dws.sql` 末尾追加汇总视图**

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS dws_indicator_daily AS
SELECT indicator_id, ref_key, as_of_date, value
FROM fact_indicator;
```

- [ ] **Step 4: 执行 DDL 并验证**

Run: `cd warehouse && for f in models/01_dim.sql models/02_ods.sql models/03_dwd.sql models/04_dws.sql; do docker exec -i warehouse-db-1 psql -U warehouse -d warehouse -v ON_ERROR_STOP=1 -q -f - < "$f" || exit 1; done`
Expected: 无报错；随后 `docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "\\dt"` 能看到 `ods_sec_submissions`、`fact_indicator` 等新表。

- [ ] **Step 5: Commit**

```bash
git add warehouse/models/
git commit -m "feat: 新增外部数据源 ODS 与通用指标模型 DDL"
```

---

### Task 2: 通用外部 ODS upsert（load_external.py）

**Files:**
- Create: `warehouse/etl/load_external.py`
- Test: `warehouse/tests/test_load_external.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_load_external.py`:

```python
"""Generic external ODS upsert tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from etl.load_external import upsert_external_rows


BATCH = f"test-ext-{uuid.uuid4()}"


@pytest.fixture
def cleanup_external(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ods_crypto_meta WHERE sync_batch_id LIKE 'test-ext-%'")
        conn.commit()


def _coin_row(coin_id: str, price: float) -> dict:
    return {
        "coin_id": coin_id,
        "symbol": coin_id.upper()[:4],
        "name": coin_id.title(),
        "snapshot_date": "2026-08-25",
        "current_price": price,
        "market_cap": price * 1000,
        "total_volume": price * 10,
        "high_24h": price * 1.1,
        "low_24h": price * 0.9,
        "market_cap_rank": 1,
        "raw_payload": {"source": "unit-test"},
        "sync_batch_id": BATCH,
    }


def test_external_upsert_is_idempotent_and_updates(dsn, cleanup_external):
    row = _coin_row("testcoin", 100.0)
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", [row])
        conn.commit()
        upsert_external_rows(conn, "crypto_meta", [_coin_row("testcoin", 120.0)])
        conn.commit()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), max(current_price) FROM ods_crypto_meta WHERE coin_id = %s",
            ("testcoin",),
        )
        count, price = cur.fetchone()
    assert count == 1
    assert price == 120.0


def test_external_upsert_rolls_back_on_bad_row(dsn, cleanup_external):
    first = _coin_row("rollback-coin", 1.0)
    second = _coin_row("bad-coin", 2.0)
    second["raw_payload"] = object()

    with psycopg.connect(dsn) as conn:
        with pytest.raises((TypeError, psycopg.Error)):
            upsert_external_rows(conn, "crypto_meta", [first, second])
        conn.rollback()

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ods_crypto_meta WHERE sync_batch_id = %s", (BATCH,))
        assert cur.fetchone()[0] == 0


def test_external_upsert_defaults_missing_raw_payload(dsn, cleanup_external):
    row = _coin_row("nopayload-coin", 1.0)
    row.pop("raw_payload")
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", [row])
        conn.commit()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT raw_payload = %s FROM ods_crypto_meta WHERE coin_id = %s",
            (Jsonb({}), "nopayload-coin"),
        )
        assert cur.fetchone()[0] is True
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_load_external.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.load_external'`

- [ ] **Step 3: 实现 `warehouse/etl/load_external.py`**

```python
"""Generic upsert helpers for external-source ODS tables."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


EXTERNAL_TABLES: dict[str, dict[str, Any]] = {
    "sec_submissions": {
        "table": "ods_sec_submissions",
        "key": ["cik"],
        "columns": ["cik", "ticker", "company_name", "exchange", "sic", "raw_payload", "sync_batch_id"],
    },
    "sec_facts": {
        "table": "ods_sec_facts",
        "key": ["cik", "concept", "unit", "period_end"],
        "columns": ["cik", "concept", "unit", "period_end", "value", "raw_payload", "sync_batch_id"],
    },
    "crypto_meta": {
        "table": "ods_crypto_meta",
        "key": ["coin_id", "snapshot_date"],
        "columns": ["coin_id", "symbol", "name", "snapshot_date", "current_price", "market_cap", "total_volume", "high_24h", "low_24h", "market_cap_rank", "raw_payload", "sync_batch_id"],
    },
    "macro_indicators": {
        "table": "ods_macro_indicators",
        "key": ["country_code", "indicator_code", "date"],
        "columns": ["country_code", "indicator_code", "indicator_name", "date", "value", "raw_payload", "sync_batch_id"],
    },
    "cn_financials": {
        "table": "ods_cn_financials",
        "key": ["symbol", "report_date", "indicator_name"],
        "columns": ["symbol", "report_date", "indicator_name", "indicator_value", "raw_payload", "sync_batch_id"],
    },
    "cn_lhb": {
        "table": "ods_cn_lhb",
        "key": ["trade_date", "code", "reason"],
        "columns": ["trade_date", "code", "name", "close_price", "change_pct", "reason", "raw_payload", "sync_batch_id"],
    },
}


def _row_params(row: dict[str, Any], columns: list[str]) -> tuple[Any, ...]:
    params: list[Any] = []
    for column in columns:
        value = row.get(column)
        if column == "raw_payload" and value is None:
            value = {}
        if column == "raw_payload" and value is not None:
            params.append(Jsonb(value))
        else:
            params.append(value)
    return tuple(params)


def upsert_external_rows(
    conn: Any, source_key: str, rows: list[dict[str, Any]], batch_size: int = 1000
) -> None:
    """Upsert external ODS rows on an open connection (caller commits)."""
    meta = EXTERNAL_TABLES.get(source_key)
    if meta is None:
        raise ValueError(f"unknown external table: {source_key}")
    if not rows:
        return
    table = meta["table"]
    columns = meta["columns"]
    key_columns = meta["key"]
    insert_columns = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_columns = ", ".join(key_columns)
    update_columns = [c for c in columns if c not in key_columns]
    assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    sql = (
        f"INSERT INTO {table} ({insert_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_columns}) DO UPDATE SET {assignments}"
    )
    with conn.cursor() as cur:
        chunk: list[tuple[Any, ...]] = []
        for row in rows:
            chunk.append(_row_params(row, columns))
            if len(chunk) >= batch_size:
                cur.executemany(sql, chunk)
                chunk.clear()
        if chunk:
            cur.executemany(sql, chunk)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_load_external.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/load_external.py warehouse/tests/test_load_external.py
git commit -m "feat: 通用外部 ODS upsert 装载"
```

---

### Task 3: SEC EDGAR 解析（sources/sec_edgar.py）

**Files:**
- Create: `warehouse/etl/sources/__init__.py`
- Create: `warehouse/etl/sources/sec_edgar.py`
- Test: `warehouse/tests/test_sources_sec.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_sec.py`:

```python
"""SEC EDGAR parsing tests."""
from __future__ import annotations

from etl.sources.sec_edgar import parse_facts, parse_submissions


SUBMISSIONS = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "exchanges": ["Nasdaq"],
    "sic": "3571",
}

FACTS = {
    "cik": "0000320193",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"end": "2025-09-27", "val": 391035000000.0},
                        {"end": "2024-09-28", "val": 383285000000.0},
                    ]
                }
            }
        }
    },
}


def test_parse_submissions_maps_company_row():
    row = parse_submissions(SUBMISSIONS)
    assert row["cik"] == "0000320193"
    assert row["ticker"] == "AAPL"
    assert row["company_name"] == "Apple Inc."
    assert row["exchange"] == "Nasdaq"
    assert row["sic"] == "3571"


def test_parse_facts_expands_concepts_without_duplicates():
    rows = list(parse_facts(FACTS))
    assert len(rows) == 2
    first = rows[0]
    assert first["cik"] == "0000320193"
    assert first["concept"] == "us-gaap/Revenues"
    assert first["unit"] == "USD"
    assert first["period_end"] == "2025-09-27"
    assert first["value"] == 391035000000.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_sec.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sources'`

- [ ] **Step 3: 实现 `warehouse/etl/sources/__init__.py`（空文件）和 `warehouse/etl/sources/sec_edgar.py`**

```python
"""SEC EDGAR fetchers and parsers."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import Request, urlopen


USER_AGENT = "finresearch-warehouse/1.0 (warehouse.etl@finresearch.local)"


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_submissions(cik: str) -> dict[str, Any]:
    return _get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")


def fetch_company_facts(cik: str) -> dict[str, Any]:
    return _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")


def parse_submissions(payload: dict[str, Any]) -> dict[str, Any]:
    tickers = payload.get("tickers") or []
    exchanges = payload.get("exchanges") or []
    return {
        "cik": payload["cik"],
        "ticker": tickers[0] if tickers else None,
        "company_name": payload["name"],
        "exchange": exchanges[0] if exchanges else None,
        "sic": payload.get("sic"),
    }


def parse_facts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    cik = payload["cik"]
    for taxonomy, concepts in (payload.get("facts") or {}).items():
        for concept, data in concepts.items():
            units = data.get("units") or {}
            for unit, entries in units.items():
                for entry in entries:
                    yield {
                        "cik": cik,
                        "concept": f"{taxonomy}/{concept}",
                        "unit": unit,
                        "period_end": entry["end"],
                        "value": entry.get("val"),
                    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_sec.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/ warehouse/tests/test_sources_sec.py
git commit -m "feat: SEC EDGAR 抓取与解析"
```

---

### Task 4: CoinGecko 解析（sources/coingecko.py）

**Files:**
- Create: `warehouse/etl/sources/coingecko.py`
- Test: `warehouse/tests/test_sources_coingecko.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_coingecko.py`:

```python
"""CoinGecko parsing tests."""
from __future__ import annotations

from etl.sources.coingecko import parse_markets


MARKETS = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "current_price": 79255.0,
        "market_cap": 1591254168516.0,
        "market_cap_rank": 1,
        "total_volume": 56842173154.0,
        "high_24h": 81160.0,
        "low_24h": 76000.0,
    }
]


def test_parse_markets_maps_snapshot_row():
    rows = list(parse_markets(MARKETS, snapshot_date="2026-08-25"))
    assert len(rows) == 1
    row = rows[0]
    assert row["coin_id"] == "bitcoin"
    assert row["symbol"] == "btc"
    assert row["name"] == "Bitcoin"
    assert row["snapshot_date"] == "2026-08-25"
    assert row["current_price"] == 79255.0
    assert row["market_cap"] == 1591254168516.0
    assert row["market_cap_rank"] == 1


def test_parse_markets_handles_empty_list():
    assert list(parse_markets([], snapshot_date="2026-08-25")) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_coingecko.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sources.coingecko'`

- [ ] **Step 3: 实现 `warehouse/etl/sources/coingecko.py`**

```python
"""CoinGecko market snapshot fetcher and parser."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import urlopen


def fetch_markets(coin_ids: list[str]) -> list[dict[str, Any]]:
    query = ",".join(coin_ids)
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        f"?vs_currency=usd&ids={query}&per_page=250"
    )
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_markets(
    payload: list[dict[str, Any]], snapshot_date: str
) -> Iterator[dict[str, Any]]:
    for item in payload:
        yield {
            "coin_id": item["id"],
            "symbol": item["symbol"],
            "name": item["name"],
            "snapshot_date": snapshot_date,
            "current_price": item.get("current_price"),
            "market_cap": item.get("market_cap"),
            "total_volume": item.get("total_volume"),
            "high_24h": item.get("high_24h"),
            "low_24h": item.get("low_24h"),
            "market_cap_rank": item.get("market_cap_rank"),
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_coingecko.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/coingecko.py warehouse/tests/test_sources_coingecko.py
git commit -m "feat: CoinGecko 行情快照抓取与解析"
```

---

### Task 5: World Bank 解析（sources/worldbank.py）

**Files:**
- Create: `warehouse/etl/sources/worldbank.py`
- Test: `warehouse/tests/test_sources_worldbank.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_worldbank.py`:

```python
"""World Bank parsing tests."""
from __future__ import annotations

from etl.sources.worldbank import parse_indicator


PAYLOAD = [
    {"page": 1, "pages": 1, "per_page": 50, "total": 1},
    [
        {
            "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
            "country": {"id": "CN", "value": "China"},
            "countryiso3code": "CHN",
            "date": "2025",
            "value": 19498039388042.6,
        }
    ],
]


def test_parse_indicator_maps_rows():
    rows = list(parse_indicator(PAYLOAD))
    assert len(rows) == 1
    row = rows[0]
    assert row["country_code"] == "CN"
    assert row["indicator_code"] == "NY.GDP.MKTP.CD"
    assert row["indicator_name"] == "GDP (current US$)"
    assert row["date"] == "2025"
    assert row["value"] == 19498039388042.6


def test_parse_indicator_skips_null_values():
    payload = [{"page": 1, "pages": 1, "per_page": 50, "total": 1}, [{"indicator": {"id": "X", "value": "X"}, "country": {"id": "CN", "value": "China"}, "countryiso3code": "CHN", "date": "2025", "value": None}]]
    assert list(parse_indicator(payload)) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_worldbank.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sources.worldbank'`

- [ ] **Step 3: 实现 `warehouse/etl/sources/worldbank.py`**

```python
"""World Bank indicator fetcher and parser."""
from __future__ import annotations

import json
from typing import Any, Iterator
from urllib.request import urlopen


def fetch_indicator(country_code: str, indicator_code: str) -> list[dict[str, Any]]:
    url = (
        "https://api.worldbank.org/v2/country/"
        f"{country_code}/indicator/{indicator_code}?format=json&per_page=100"
    )
    with urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_indicator(payload: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    records = payload[1] if len(payload) > 1 else []
    for item in records:
        value = item.get("value")
        if value is None:
            continue
        yield {
            "country_code": item["country"]["id"],
            "indicator_code": item["indicator"]["id"],
            "indicator_name": item["indicator"]["value"],
            "date": item["date"],
            "value": value,
        }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_worldbank.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/worldbank.py warehouse/tests/test_sources_worldbank.py
git commit -m "feat: World Bank 宏观指标抓取与解析"
```

---

### Task 6: akshare 解析（sources/akshare_cn.py）

**Files:**
- Create: `warehouse/etl/sources/akshare_cn.py`
- Test: `warehouse/tests/test_sources_akshare_cn.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_akshare_cn.py`:

```python
"""akshare China A-share parsing tests."""
from __future__ import annotations

from etl.sources.akshare_cn import parse_financials, parse_lhb


FINANCIALS = [
    {"报告期": "2025-12-31", "净利润": 862.3, "营业总收入": 1708.0, "净利润同比增长率": 15.2},
    {"报告期": "2025-09-30", "净利润": 600.1, "营业总收入": 1250.0, "净利润同比增长率": 12.8},
]

LHB = [
    {"上榜日": "2026-08-21", "代码": "600519", "名称": "贵州茅台", "解读": "日涨幅偏离值达7%", "收盘价": 1450.0, "涨跌幅": 8.5},
]


def test_parse_financials_expands_wide_rows():
    rows = list(parse_financials(FINANCIALS, symbol="600519"))
    assert len(rows) == 6
    assert {"symbol": "600519", "report_date": "2025-12-31", "indicator_name": "净利润", "indicator_value": 862.3} in rows


def test_parse_lhb_maps_rows():
    rows = list(parse_lhb(LHB))
    assert len(rows) == 1
    row = rows[0]
    assert row["trade_date"] == "2026-08-21"
    assert row["code"] == "600519"
    assert row["name"] == "贵州茅台"
    assert row["reason"] == "日涨幅偏离值达7%"
    assert row["close_price"] == 1450.0
    assert row["change_pct"] == 8.5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_akshare_cn.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sources.akshare_cn'`

- [ ] **Step 3: 实现 `warehouse/etl/sources/akshare_cn.py`**

```python
"""akshare China A-share fetchers and parsers (lazy import to keep CLI light)."""
from __future__ import annotations

from typing import Any, Iterator


FINANCIAL_INDICATORS = ("净利润", "净利润同比增长率", "扣非净利润", "营业总收入")


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def fetch_financials(symbol: str) -> list[dict[str, Any]]:
    frame = _ak().stock_financial_abstract_ths(symbol=symbol)
    return frame.to_dict("records")


def fetch_lhb(start_date: str, end_date: str) -> list[dict[str, Any]]:
    frame = _ak().stock_lhb_detail_em(start_date=start_date, end_date=end_date)
    return frame.to_dict("records")


def parse_financials(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        report_date = record.get("报告期")
        for indicator in FINANCIAL_INDICATORS:
            value = record.get(indicator)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            yield {
                "symbol": symbol,
                "report_date": str(report_date),
                "indicator_name": indicator,
                "indicator_value": numeric,
            }


def parse_lhb(records: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for record in records:
        yield {
            "trade_date": str(record["上榜日"]),
            "code": str(record["代码"]),
            "name": str(record["名称"]),
            "close_price": _to_float(record.get("收盘价")),
            "change_pct": _to_float(record.get("涨跌幅")),
            "reason": str(record.get("解读") or ""),
        }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sources_akshare_cn.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/akshare_cn.py warehouse/tests/test_sources_akshare_cn.py
git commit -m "feat: akshare A股财务与龙虎榜抓取解析"
```

---

### Task 7: 指标模型构建（build_indicator.py）

**Files:**
- Create: `warehouse/etl/build_indicator.py`
- Test: `warehouse/tests/test_build_indicator.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_build_indicator.py`:

```python
"""Indicator model build tests."""
from __future__ import annotations

import uuid

import psycopg
import pytest

from etl.build_indicator import build_indicators
from etl.load_external import upsert_external_rows


BATCH = f"test-ind-{uuid.uuid4()}"


@pytest.fixture
def cleanup_indicator(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM ods_crypto_meta WHERE sync_batch_id LIKE 'test-ind-%'")
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator WHERE source = 'crypto'
            )
            """
        )
        cur.execute("DELETE FROM dim_indicator WHERE source = 'crypto'")
        conn.commit()


def _seed_crypto(dsn: str) -> None:
    rows = [
        {
            "coin_id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "snapshot_date": "2026-08-25",
            "current_price": 79000.0,
            "market_cap": 1.5e12,
            "total_volume": 5.0e10,
            "high_24h": 80000.0,
            "low_24h": 78000.0,
            "market_cap_rank": 1,
            "raw_payload": {},
            "sync_batch_id": BATCH,
        }
    ]
    with psycopg.connect(dsn) as conn:
        upsert_external_rows(conn, "crypto_meta", rows)
        conn.commit()


def test_build_indicators_creates_dim_and_fact(dsn, cleanup_indicator):
    _seed_crypto(dsn)
    with psycopg.connect(dsn) as conn:
        affected = build_indicators(conn, "crypto")
        conn.commit()

    assert affected == 3
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_indicator WHERE source = 'crypto'")
        assert cur.fetchone()[0] == 3
        cur.execute(
            """
            SELECT i.source_key, f.ref_key, f.value
            FROM fact_indicator f
            JOIN dim_indicator i ON i.indicator_id = f.indicator_id
            WHERE i.source = 'crypto' AND i.source_key = 'current_price'
            """
        )
        assert cur.fetchone() == ("current_price", "bitcoin", 79000.0)


def test_build_indicators_is_idempotent(dsn, cleanup_indicator):
    _seed_crypto(dsn)
    with psycopg.connect(dsn) as conn:
        build_indicators(conn, "crypto")
        build_indicators(conn, "crypto")
        conn.commit()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_indicator WHERE source = 'crypto'")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT count(*) FROM fact_indicator")
        assert cur.fetchone()[0] == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_build_indicator.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.build_indicator'`

- [ ] **Step 3: 实现 `warehouse/etl/build_indicator.py`**

```python
"""Build dim_indicator / fact_indicator from external ODS tables."""
from __future__ import annotations

from datetime import date
from typing import Any, Iterator

from psycopg.rows import dict_row


def _parse_date(value: str) -> date:
    text = str(value).strip()
    if len(text) == 4:  # World Bank 年份
        return date(int(text), 1, 1)
    return date.fromisoformat(text)


def _iter_rows(cur: Any, source: str) -> Iterator[tuple[str, str, str, str, date, float]]:
    """Yield (source_key, name, unit, ref_key, as_of_date, value)."""
    if source == "crypto":
        cur.execute(
            """
            SELECT coin_id, snapshot_date, current_price, market_cap, total_volume
            FROM ods_crypto_meta
            """
        )
        for row in cur.fetchall():
            coin_id, snapshot, price, cap, volume = row
            for source_key, name, value in (
                ("current_price", "当前价格", price),
                ("market_cap", "市值", cap),
                ("total_volume", "24h 成交量", volume),
            ):
                if value is None:
                    continue
                yield source_key, name, "USD", coin_id, snapshot, value
    elif source == "macro":
        cur.execute(
            """
            SELECT indicator_code, indicator_name, country_code, date, value
            FROM ods_macro_indicators
            """
        )
        for row in cur.fetchall():
            code, name, country, period, value = row
            yield code, name, None, country, _parse_date(period), value
    elif source == "sec":
        cur.execute(
            "SELECT concept, unit, cik, period_end, value FROM ods_sec_facts"
        )
        for row in cur.fetchall():
            concept, unit, cik, period_end, value = row
            yield concept, concept, unit, cik, period_end, value
    elif source == "cn-finance":
        cur.execute(
            """
            SELECT indicator_name, symbol, report_date, indicator_value
            FROM ods_cn_financials
            """
        )
        for row in cur.fetchall():
            name, symbol, period, value = row
            yield name, name, None, symbol, _parse_date(period), value
    elif source == "cn-lhb":
        cur.execute(
            "SELECT code, trade_date, close_price, change_pct FROM ods_cn_lhb"
        )
        for row in cur.fetchall():
            code, trade_date, close_price, change_pct = row
            for source_key, name, value in (
                ("close_price", "龙虎榜收盘价", close_price),
                ("change_pct", "龙虎榜涨跌幅", change_pct),
            ):
                if value is None:
                    continue
                yield source_key, name, None, code, _parse_date(trade_date), value
    else:
        raise ValueError(f"unknown indicator source: {source}")


def build_indicators(conn: Any, source: str) -> int:
    """Upsert dim/fact indicators from one ODS source on an open connection."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT indicator_id, source_key FROM dim_indicator WHERE source = %s", (source,))
        cache = {row["source_key"]: row["indicator_id"] for row in cur.fetchall()}
        affected = 0
        for source_key, name, unit, ref_key, as_of_date, value in _iter_rows(cur, source):
            indicator_id = cache.get(source_key)
            if indicator_id is None:
                cur.execute(
                    """
                    INSERT INTO dim_indicator (source, source_key, name, unit)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source, source_key) DO UPDATE SET
                      name = EXCLUDED.name, unit = EXCLUDED.unit
                    RETURNING indicator_id
                    """,
                    (source, source_key, name, unit),
                )
                indicator_id = cur.fetchone()["indicator_id"]
                cache[source_key] = indicator_id
            cur.execute(
                """
                INSERT INTO fact_indicator (indicator_id, ref_key, as_of_date, value)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (indicator_id, ref_key, as_of_date) DO UPDATE SET
                  value = EXCLUDED.value
                """,
                (indicator_id, ref_key, as_of_date, value),
            )
            affected += cur.rowcount
        return affected
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_build_indicator.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/build_indicator.py warehouse/tests/test_build_indicator.py
git commit -m "feat: 通用指标模型构建 dim_indicator/fact_indicator"
```

---

### Task 8: 每日增量入口（sync_external.py）

**Files:**
- Create: `warehouse/etl/sync_external.py`
- Test: `warehouse/tests/test_sync_external.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sync_external.py`:

```python
"""External sync orchestration tests."""
from __future__ import annotations

from datetime import date, timedelta
import uuid

import psycopg
import pytest

from etl.db import connect
from etl.sync_external import get_watermark, sync_external, sync_coingecko


@pytest.fixture
def cleanup_external_sync(dsn):
    yield
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for table in ("ods_crypto_meta", "ods_sec_submissions", "ods_sec_facts",
                      "ods_macro_indicators", "ods_cn_financials", "ods_cn_lhb"):
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-extsync-%'")
        cur.execute(
            "DELETE FROM fact_indicator WHERE indicator_id IN (SELECT indicator_id FROM dim_indicator WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb'))"
        )
        cur.execute("DELETE FROM dim_indicator WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb')")
        cur.execute("DELETE FROM etl_watermarks WHERE scope LIKE 'coingecko:%' OR scope LIKE 'sec:%' OR scope LIKE 'worldbank:%' OR scope LIKE 'akshare:%'")
        conn.commit()


def _fake_markets(_ids):
    return [
        {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "current_price": 79000.0,
            "market_cap": 1.5e12,
            "total_volume": 5.0e10,
            "high_24h": 80000.0,
            "low_24h": 78000.0,
            "market_cap_rank": 1,
        }
    ]


def test_sync_coingecko_first_run_then_incremental(dsn, cleanup_external_sync, monkeypatch):
    from etl.sources import coingecko

    monkeypatch.setattr(coingecko, "fetch_markets", _fake_markets)
    with connect(dsn) as conn:
        stats = sync_coingecko(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()
    assert stats["rows"] == 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ods_crypto_meta WHERE coin_id = 'bitcoin'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM fact_indicator")
        assert cur.fetchone()[0] == 3

    with connect(dsn) as conn:
        second = sync_coingecko(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()
    assert second["rows"] == 0  # 同一天快照已存在，增量跳过


def test_sync_external_failed_source_does_not_block_others(dsn, cleanup_external_sync, monkeypatch):
    from etl.sources import coingecko, worldbank

    monkeypatch.setattr(coingecko, "fetch_markets", _fake_markets)

    def boom(_country, _code):
        raise RuntimeError("network down")

    monkeypatch.setattr(worldbank, "fetch_indicator", boom)
    stats = sync_external(dsn, batch_id=f"test-extsync-{uuid.uuid4()}")
    assert stats["coingecko"]["status"] == "ok"
    assert stats["worldbank"]["status"] == "error"


def test_get_watermark_missing_scope_returns_none(dsn):
    with psycopg.connect(dsn) as conn:
        assert get_watermark(conn, "coingecko:coin:does-not-exist") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sync_external.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sync_external'`

- [ ] **Step 3: 实现 `warehouse/etl/sync_external.py`**

```python
"""Daily incremental sync for external indicator sources."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
from typing import Any, Callable

from etl.build_indicator import build_indicators
from etl.db import connect
from etl.load_external import upsert_external_rows
from etl.migrate_seed import _new_batch_id, DEFAULT_DSN
from etl.sources import akshare_cn, coingecko, sec_edgar, worldbank


logger = logging.getLogger(__name__)


def get_watermark(conn: Any, scope: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT last_value FROM etl_watermarks WHERE scope = %s", (scope,))
        row = cur.fetchone()
    return row[0] if row else None


def set_watermark(conn: Any, scope: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermarks (scope, last_value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (scope) DO UPDATE SET
              last_value = EXCLUDED.last_value, updated_at = now()
            """,
            (scope, value),
        )


def _run_source(dsn: str, batch_id: str, fn: Callable[[Any, str], dict[str, Any]]) -> dict[str, Any]:
    with connect(dsn) as conn:
        try:
            stats = fn(conn, batch_id)
            conn.commit()
            return {**stats, "status": "ok"}
        except Exception as exc:  # noqa: BLE001 - 单源失败不阻塞其他源
            conn.rollback()
            logger.warning("external source failed: %s", exc)
            return {"status": "error", "error": str(exc)}


def sync_coingecko(conn: Any, batch_id: str) -> dict[str, Any]:
    today = date.today().isoformat()
    scope = f"coingecko:snapshot:{today}"
    if get_watermark(conn, scope) is not None:
        return {"rows": 0}
    coin_ids = ["bitcoin", "ethereum", "solana", "binancecoin"]
    rows = [
        {**row, "raw_payload": {}, "sync_batch_id": batch_id}
        for row in coingecko.parse_markets(coingecko.fetch_markets(coin_ids), today)
    ]
    if rows:
        upsert_external_rows(conn, "crypto_meta", rows)
        build_indicators(conn, "crypto")
    set_watermark(conn, scope, today)
    return {"rows": len(rows)}


def sync_sec(conn: Any, batch_id: str) -> dict[str, Any]:
    ciks = ["0000320193", "0001045810", "0000789019", "0001318605"]  # AAPL NVDA MSFT TSLA
    submissions_rows = []
    facts_rows = []
    for cik in ciks:
        scope = f"sec:cik:{cik}"
        if get_watermark(conn, scope) is not None:
            continue
        submissions_rows.append({**sec_edgar.parse_submissions(sec_edgar.fetch_submissions(cik)), "raw_payload": {}, "sync_batch_id": batch_id})
        facts_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in sec_edgar.parse_facts(sec_edgar.fetch_company_facts(cik))
        )
        set_watermark(conn, scope, date.today().isoformat())
    if submissions_rows:
        upsert_external_rows(conn, "sec_submissions", submissions_rows)
    if facts_rows:
        upsert_external_rows(conn, "sec_facts", facts_rows)
        build_indicators(conn, "sec")
    return {"submissions": len(submissions_rows), "facts": len(facts_rows)}


def sync_worldbank(conn: Any, batch_id: str) -> dict[str, Any]:
    indicators = ["NY.GDP.MKTP.CD", "FP.CPI.TOTL.ZG", "FR.INR.LEND"]
    rows = []
    for code in indicators:
        scope = f"worldbank:series:{code}"
        if get_watermark(conn, scope) is not None:
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in worldbank.parse_indicator(worldbank.fetch_indicator("CN", code))
        )
        set_watermark(conn, scope, date.today().isoformat())
    if rows:
        upsert_external_rows(conn, "macro_indicators", rows)
        build_indicators(conn, "macro")
    return {"rows": len(rows)}


def sync_akshare(conn: Any, batch_id: str) -> dict[str, Any]:
    symbols = ["600519", "000001", "300750", "601318", "600036"]
    finance_rows = []
    for symbol in symbols:
        scope = f"akshare:finance:{symbol}"
        if get_watermark(conn, scope) is not None:
            continue
        finance_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in akshare_cn.parse_financials(akshare_cn.fetch_financials(symbol), symbol)
        )
        set_watermark(conn, scope, date.today().isoformat())
    if finance_rows:
        upsert_external_rows(conn, "cn_financials", finance_rows)
        build_indicators(conn, "cn-finance")

    lhb_rows = []
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=29)
    lhb_scope = "akshare:lhb"
    last = get_watermark(conn, lhb_scope)
    if last:
        start = max(start, date.fromisoformat(last) + timedelta(days=1))
    if start <= end:
        lhb_rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in akshare_cn.parse_lhb(akshare_cn.fetch_lhb(start.isoformat().replace("-", ""), end.isoformat().replace("-", "")))
        )
        if lhb_rows:
            upsert_external_rows(conn, "cn_lhb", lhb_rows)
            build_indicators(conn, "cn-lhb")
        set_watermark(conn, lhb_scope, end.isoformat())
    return {"finance": len(finance_rows), "lhb": len(lhb_rows)}


def sync_external(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or _new_batch_id()
    return {
        "coingecko": _run_source(dsn, batch_id, sync_coingecko),
        "sec": _run_source(dsn, batch_id, sync_sec),
        "worldbank": _run_source(dsn, batch_id, sync_worldbank),
        "akshare": _run_source(dsn, batch_id, sync_akshare),
    }


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    stats = sync_external(dsn)
    for source, result in stats.items():
        print(f"{source}: {result}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd warehouse && .venv/bin/python -m pytest tests/test_sync_external.py -q`
Expected: `3 passed`

- [ ] **Step 5: 跑全量测试确认无回归**

Run: `cd warehouse && .venv/bin/python -m pytest tests -q`
Expected: 全部通过（原 54 + 新增）

- [ ] **Step 6: Commit**

```bash
git add warehouse/etl/sync_external.py warehouse/tests/test_sync_external.py
git commit -m "feat: 外部数据源每日增量同步入口"
```

---

### Task 9: 依赖与文档

**Files:**
- Modify: `warehouse/requirements.txt`
- Modify: `warehouse/README.md`

- [ ] **Step 1: `warehouse/requirements.txt` 增加 akshare**

```text
psycopg[binary]>=3.1
pytest>=8.0
akshare>=1.18
```

- [ ] **Step 2: `warehouse/README.md` 增加外部数据源小节**

```markdown
## 运行外部数据源同步

接入 SEC EDGAR（美股财报）、CoinGecko（加密市值）、World Bank（宏观指标）与
akshare（A股财务/龙虎榜），每日增量：

```bash
cd warehouse
python -m etl.sync_external
```

各源按独立事务装载并维护 `etl_watermarks` 水位线，失败仅回滚对应源。
```

- [ ] **Step 3: 更新 README 的 cron 示例为两个命令**

```cron
0 9 * * * cd /path/to/finresearch/warehouse && WAREHOUSE_DSN="$WAREHOUSE_DSN" .venv/bin/python -m etl.sync_incremental && .venv/bin/python -m etl.sync_external
```

- [ ] **Step 4: Commit**

```bash
git add warehouse/requirements.txt warehouse/README.md
git commit -m "docs: 外部数据源同步依赖与运行说明"
```

---

### Task 10: 端到端验证

- [ ] **Step 1: 安装依赖并执行真实同步**

Run: `cd warehouse && .venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple akshare && WAREHOUSE_DSN=postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse .venv/bin/python -m etl.sync_external`
Expected: 四个源均输出 `status: ok`，akshare 财务约 103 行/股、龙虎榜若干行。

- [ ] **Step 2: 验证落库**

Run: `docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "SELECT source, count(*) FROM dim_indicator GROUP BY source" -c "SELECT count(*) FROM fact_indicator" -c "SELECT count(*) FROM ods_sec_submissions" -c "SELECT count(*) FROM ods_cn_financials"`
Expected: 各源有数据；`fact_indicator` 行数与 ODS 展开一致。

- [ ] **Step 3: 验证增量幂等**

Run: `cd warehouse && WAREHOUSE_DSN=postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse .venv/bin/python -m etl.sync_external`
Expected: CoinGecko/SEC/World Bank 当日水位线已存在，`rows: 0`；akshare 财务同样跳过。

- [ ] **Step 4: 更新 ARCHITECTURE.md 数仓小节**

在 `docs/ARCHITECTURE.md` 数仓小节补充一行：外部数据源（SEC/CoinGecko/World Bank/akshare）经 `sync_external` 入 ODS → `dim_indicator`/`fact_indicator` → `dws_indicator_daily`。

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs: 架构文档同步外部数据源链路"
```
