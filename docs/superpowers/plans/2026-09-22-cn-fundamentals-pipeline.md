# A股基本面指标采集 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把总资产、净资产(归母/合计)、总市值、换手率四个字段接入 warehouse 数仓的通用指标模型，并修复外部源水位线永久跳过的缺陷。

**Architecture:** 新增两个独立数据源（新浪资产负债表、东财股本结构），按项目既有的"一源一文件 → ODS 贴源表 → build_indicators → dim/fact_indicator"链路接入。换手率与总市值不新增采集，由既有 84 万行 K 线配合股本数据计算得出。水位线统一改为「scope 稳定 + 值存 ISO 周」。

**Tech Stack:** Python 3.11、psycopg 3、pytest、akshare（惰性导入）、PostgreSQL（docker 容器 `warehouse-db-1`）

**Spec:** `docs/superpowers/specs/2026-09-22-cn-fundamentals-pipeline-design.md`

## Global Constraints

- 所有测试与命令在 `warehouse/` 目录下执行；该目录**没有** `.venv`，必须使用 `/Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python`。
- 测试库为 `warehouse_test`，真实库为 `warehouse`。DDL 变更必须**同时**应用到两个库。
- **测试 fixture 必须使用真实响应形状**（带单位字符串、NaN 列、真实中文列名）。禁止使用简化过的纯数字 mock——本项目已因此发生过一次严重逃逸。
- 解析失败一律**跳过**，不写 0、不写 NaN。
- 新增 source 的 key 固定为 `cn-balance` 与 `cn-daily`。
- 指标名固定为：`总资产`、`净资产(归母)`、`净资产(合计)`、`换手率`、`总市值`。
- 换手率单位约定为百分数（`0.200123` 表示 0.200123%）。
- 提交信息用中文，格式 `<类型>: <简短描述>`，类型取 `feat`/`fix`/`refactor`/`docs`/`chore`/`style`。
- akshare 必须惰性导入（`import akshare` 放在函数内），保持 CLI 轻量。

---

### Task 1: 新浪资产负债表源

**Files:**
- Create: `warehouse/etl/sources/sina_cn.py`
- Test: `warehouse/tests/test_sources_sina_cn.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `sina_symbol(code: str) -> str` — 6/9 开头加 `sh`，0/3 开头加 `sz`，4/8 开头抛 `ValueError`
  - `fetch_balance_sheet(code: str) -> list[dict]` — 调 `ak.stock_financial_report_sina(stock=sina_symbol(code), symbol="资产负债表")`
  - `parse_balance_sheet(records: list[dict], symbol: str) -> Iterator[dict]` — 产出 `{"symbol", "report_date", "indicator_name", "indicator_value"}`

背景：新浪该接口返回**宽表**（一行一报告期），列包含 `报告日`（`YYYYMMDD` 字符串）、`资产总计`、`归属于母公司股东权益合计`、`所有者权益(或股东权益)合计`。注意 `所有者权益` 这一列实测**全为 NaN**，必须用带括号的那个，且 NaN 不得落库。

- [ ] **Step 1: Write the failing test**

创建 `warehouse/tests/test_sources_sina_cn.py`：

```python
"""Sina balance sheet source tests."""
from __future__ import annotations

import math

import pytest

from etl.sources.sina_cn import parse_balance_sheet, sina_symbol


BALANCE_SHEET = [
    {
        "报告日": "20260630",
        "资产总计": 309050784569.31,
        "负债合计": 46954432394.95,
        "所有者权益": math.nan,
        "归属于母公司股东权益合计": 251253594419.5,
        "所有者权益(或股东权益)合计": 262096352174.36,
    },
    {
        "报告日": "20260331",
        "资产总计": 319918844905.58,
        "所有者权益": math.nan,
        "归属于母公司股东权益合计": 270894035676.27,
        "所有者权益(或股东权益)合计": 281135886435.69,
    },
]


def test_sina_symbol_maps_market_prefix():
    assert sina_symbol("600519") == "sh600519"
    assert sina_symbol("000001") == "sz000001"
    assert sina_symbol("300750") == "sz300750"


def test_sina_symbol_rejects_beijing_exchange():
    with pytest.raises(ValueError):
        sina_symbol("830799")


def test_parse_balance_sheet_emits_three_indicators_per_period():
    rows = list(parse_balance_sheet(BALANCE_SHEET, symbol="600519"))
    assert len(rows) == 6
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "总资产",
        "indicator_value": 309050784569.31,
    } in rows
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "净资产(归母)",
        "indicator_value": 251253594419.5,
    } in rows
    assert {
        "symbol": "600519",
        "report_date": "2026-06-30",
        "indicator_name": "净资产(合计)",
        "indicator_value": 262096352174.36,
    } in rows


def test_parse_balance_sheet_skips_nan_column():
    """`所有者权益` 列实测为 NaN，不得产出任何指标行。"""
    records = [{"报告日": "20260630", "所有者权益": math.nan}]
    assert list(parse_balance_sheet(records, symbol="600519")) == []


def test_parse_balance_sheet_skips_missing_indicator():
    records = [{"报告日": "20260630", "资产总计": 100.0}]
    assert list(parse_balance_sheet(records, symbol="600519")) == [
        {
            "symbol": "600519",
            "report_date": "2026-06-30",
            "indicator_name": "总资产",
            "indicator_value": 100.0,
        }
    ]


def test_parse_balance_sheet_skips_malformed_report_date():
    records = [{"报告日": "2026-06-30", "资产总计": 100.0}]
    assert list(parse_balance_sheet(records, symbol="600519")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_sina_cn.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etl.sources.sina_cn'`

- [ ] **Step 3: Write minimal implementation**

创建 `warehouse/etl/sources/sina_cn.py`：

```python
"""Sina A-share balance sheet source (lazy import to keep CLI light)."""
from __future__ import annotations

import math
from typing import Any, Iterator


BALANCE_COLUMNS = (
    ("资产总计", "总资产"),
    ("归属于母公司股东权益合计", "净资产(归母)"),
    ("所有者权益(或股东权益)合计", "净资产(合计)"),
)


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def sina_symbol(code: str) -> str:
    """A 股 6 位代码转新浪带前缀代码；北交所不支持。"""
    text = str(code).strip()
    if text.startswith(("6", "9")):
        return f"sh{text}"
    if text.startswith(("0", "3")):
        return f"sz{text}"
    raise ValueError(f"sina does not support A-share code: {code}")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _format_report_date(value: Any) -> str | None:
    text = str(value).strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:]}"


def fetch_balance_sheet(code: str) -> list[dict[str, Any]]:
    frame = _ak().stock_financial_report_sina(
        stock=sina_symbol(code), symbol="资产负债表"
    )
    return frame.to_dict("records")


def parse_balance_sheet(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        report_date = _format_report_date(record.get("报告日"))
        if report_date is None:
            continue
        for column, indicator in BALANCE_COLUMNS:
            value = _to_float(record.get(column))
            if value is None:
                continue
            yield {
                "symbol": symbol,
                "report_date": report_date,
                "indicator_name": indicator,
                "indicator_value": value,
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_sina_cn.py -q`

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/sina_cn.py warehouse/tests/test_sources_sina_cn.py
git commit -m "feat: 新增新浪资产负债表源"
```

---

### Task 2: 东财股本结构源

**Files:**
- Create: `warehouse/etl/sources/eastmoney_cn.py`
- Test: `warehouse/tests/test_sources_eastmoney_cn.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `fetch_share_structure(code: str) -> list[dict]` — 调 `ak.stock_zh_a_gbjg_em(symbol=code)`
  - `parse_share_structure(records: list[dict], symbol: str) -> Iterator[dict]` — 产出 `{"symbol", "change_date", "total_shares", "float_shares"}`

背景：该接口返回多期股本变更记录，列名为 `变更日期`（`YYYY-MM-DD`）、`总股本`、`已流通股份`。实测茅台返回 16 条。`已流通股份` 缺失时同样跳过（不写 0）。

- [ ] **Step 1: Write the failing test**

创建 `warehouse/tests/test_sources_eastmoney_cn.py`：

```python
"""Eastmoney share structure source tests."""
from __future__ import annotations

import math

from etl.sources.eastmoney_cn import parse_share_structure


SHARE_STRUCTURE = [
    {
        "变更日期": "2026-05-28",
        "总股本": 1250081601,
        "流通受限股份": 0.0,
        "已流通股份": 1250081601,
        "变动原因": "回购",
    },
    {
        "变更日期": "2025-09-01",
        "总股本": 1252270215,
        "流通受限股份": 0.0,
        "已流通股份": 1252270215,
        "变动原因": "回购",
    },
]


def test_parse_share_structure_maps_real_columns():
    rows = list(parse_share_structure(SHARE_STRUCTURE, symbol="600519"))
    assert rows == [
        {
            "symbol": "600519",
            "change_date": "2026-05-28",
            "total_shares": 1250081601.0,
            "float_shares": 1250081601.0,
        },
        {
            "symbol": "600519",
            "change_date": "2025-09-01",
            "total_shares": 1252270215.0,
            "float_shares": 1252270215.0,
        },
    ]


def test_parse_share_structure_skips_missing_total_shares():
    records = [{"变更日期": "2026-05-28", "总股本": math.nan, "已流通股份": 100.0}]
    assert list(parse_share_structure(records, symbol="600519")) == []


def test_parse_share_structure_keeps_null_float_shares():
    """流通股本缺失时仍保留总股本（总市值可用），float_shares 为 None。"""
    records = [{"变更日期": "2026-05-28", "总股本": 1000.0}]
    assert list(parse_share_structure(records, symbol="600519")) == [
        {
            "symbol": "600519",
            "change_date": "2026-05-28",
            "total_shares": 1000.0,
            "float_shares": None,
        }
    ]


def test_parse_share_structure_skips_missing_change_date():
    records = [{"总股本": 1000.0, "已流通股份": 1000.0}]
    assert list(parse_share_structure(records, symbol="600519")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_eastmoney_cn.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etl.sources.eastmoney_cn'`

- [ ] **Step 3: Write minimal implementation**

创建 `warehouse/etl/sources/eastmoney_cn.py`：

```python
"""Eastmoney A-share share structure source (lazy import to keep CLI light)."""
from __future__ import annotations

import math
from typing import Any, Iterator


def _ak() -> Any:
    import akshare  # lazy: heavy dependency

    return akshare


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def fetch_share_structure(code: str) -> list[dict[str, Any]]:
    frame = _ak().stock_zh_a_gbjg_em(symbol=code)
    return frame.to_dict("records")


def parse_share_structure(
    records: list[dict[str, Any]], symbol: str
) -> Iterator[dict[str, Any]]:
    for record in records:
        change_date = str(record.get("变更日期") or "").strip()
        total_shares = _to_float(record.get("总股本"))
        if not change_date or total_shares is None:
            continue
        yield {
            "symbol": symbol,
            "change_date": change_date,
            "total_shares": total_shares,
            "float_shares": _to_float(record.get("已流通股份")),
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_eastmoney_cn.py -q`

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/eastmoney_cn.py warehouse/tests/test_sources_eastmoney_cn.py
git commit -m "feat: 新增东财股本结构源"
```

---

### Task 3: 水位线判据修复（周粒度）

**Files:**
- Modify: `warehouse/etl/sync_external.py`（`sync_sec` 约 70-95 行、`sync_worldbank` 约 98-113 行、`sync_akshare` 约 116-155 行）
- Test: `warehouse/tests/test_sync_external.py`

**Interfaces:**
- Consumes: `get_watermark(conn, scope) -> str | None`、`set_watermark(conn, scope, value) -> None`（文件内既有）
- Produces: `iso_week(today: date | None = None) -> str` — 返回 `'2026-W39'` 形式

背景：现有判据是 `if get_watermark(conn, scope) is not None: continue`，scope 不含时间粒度，导致 sec / worldbank / akshare-finance **首次采集后永久跳过**。改为「值等于当前 ISO 周则跳过」。

**迁移行为（预期，勿"修复"）**：库里现有值是日期（如 `2026-09-22`），与 ISO 周永不相等，因此改动后首次运行会全量重采一次。这正是期望行为。

- [ ] **Step 1: Write the failing test**

在 `warehouse/tests/test_sync_external.py` **末尾追加**（该文件的 `cleanup_external_sync` 夹具已清理 `sec:%` / `worldbank:%` / `akshare:%` 水位线，可直接复用）：

```python
def test_iso_week_formats_with_zero_padded_week():
    from datetime import date

    from etl.sync_external import iso_week

    assert iso_week(date(2026, 9, 22)) == "2026-W39"
    assert iso_week(date(2026, 1, 5)) == "2026-W02"


def test_sync_worldbank_skips_within_same_week(dsn, cleanup_external_sync, monkeypatch):
    from etl.sources import worldbank

    calls: list[str] = []

    def _fake(_country: str, code: str) -> list[dict]:
        calls.append(code)
        return [{"date": "2024", "value": 1.0, "indicator_name": code}]

    monkeypatch.setattr(worldbank, "fetch_indicator", _fake)
    batch = f"test-extsync-{uuid.uuid4()}"

    with connect(dsn) as conn:
        first = sync_worldbank(conn, batch_id=batch)
        conn.commit()
    assert len(calls) == 3  # 三个指标各取一次

    calls.clear()
    with connect(dsn) as conn:
        second = sync_worldbank(conn, batch_id=batch)
        conn.commit()
    assert calls == []  # 同一周内全部跳过
    assert second["rows"] == 0
```

同时把文件顶部导入行改为：

```python
from etl.sync_external import (
    get_watermark,
    sync_coingecko,
    sync_external,
    sync_worldbank,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sync_external.py -q -k "iso_week or same_week"`

Expected: FAIL — `ImportError: cannot import name 'iso_week'`

- [ ] **Step 3: Write minimal implementation**

在 `warehouse/etl/sync_external.py` 的 `set_watermark` 之后加入：

```python
def iso_week(today: date | None = None) -> str:
    """返回 ISO 周标识，如 '2026-W39'，用作周粒度的水位线值。"""
    iso = (today or date.today()).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
```

然后把三个源的判据与写入改为周粒度：

`sync_sec` 内：

```python
    week = iso_week()
    for cik in ciks:
        scope = f"sec:cik:{cik}"
        if get_watermark(conn, scope) == week:
            continue
        # ... 既有采集逻辑不变 ...
        set_watermark(conn, scope, week)
```

`sync_worldbank` 内：

```python
    week = iso_week()
    for code in indicators:
        scope = f"worldbank:series:{code}"
        if get_watermark(conn, scope) == week:
            continue
        # ... 既有采集逻辑不变 ...
        set_watermark(conn, scope, week)
```

`sync_akshare` 的财务段内（`lhb` 段**不要动**，它用的是正确的日期增量）：

```python
    week = iso_week()
    for symbol in symbols:
        scope = f"akshare:finance:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        # ... 既有采集逻辑不变 ...
        set_watermark(conn, scope, week)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sync_external.py -q`

Expected: 全部通过（含既有的 4 个测试 + 新增 3 个，共 7 个，无回归）

> 注：新增测试必须包含**跨周重采**一例。仅测「同周跳过」不足以保护本次修复——旧实现的「永久跳过」天然包含「同周跳过」，该测试在旧实现下同样通过。跨周用例必须在旧实现下失败。

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sync_external.py warehouse/tests/test_sync_external.py
git commit -m "fix: 修复外部源水位线永久跳过

sec/worldbank/akshare 财务的 scope 不含时间粒度，首次采集后
永久跳过，季度更新的财务数据永不刷新。改为按 ISO 周判定。"
```

---

### Task 4: 两个新源接入管线

**Files:**
- Modify: `warehouse/models/02_ods.sql`（追加两张表）
- Modify: `warehouse/etl/load_external.py`（`EXTERNAL_TABLES` 追加两项）
- Modify: `warehouse/etl/build_indicator.py`（`_iter_rows` 追加 `cn-balance` 分支）
- Modify: `warehouse/etl/sync_external.py`（追加 `_a_share_universe`、`sync_balance_sheet`、`sync_share_structure`，并注册进 `sync_external`）
- Test: `warehouse/tests/test_sync_external.py`（追加）、`warehouse/tests/test_build_indicator.py`（追加）

**Interfaces:**
- Consumes: `sina_cn.parse_balance_sheet`、`sina_cn.fetch_balance_sheet`（Task 1）、`eastmoney_cn.parse_share_structure`、`eastmoney_cn.fetch_share_structure`（Task 2）、`iso_week()`（Task 3）
- Produces:
  - `_a_share_universe() -> list[str]` — 返回 6 位 A 股代码
  - `sync_balance_sheet(conn, batch_id) -> dict` — 返回 `{"rows": int, "failed": int}`
  - `sync_share_structure(conn, batch_id) -> dict` — 返回 `{"rows": int, "failed": int}`
  - `METRICS_SCOPE = "cn-daily:metrics"` 常量（供 Task 5 引用）
  - 指标 source `cn-balance`，含 `总资产`、`净资产(归母)`、`净资产(合计)`

- [ ] **Step 1: 追加 DDL 并应用到两个库**

在 `warehouse/models/02_ods.sql` **末尾追加**：

```sql
CREATE TABLE IF NOT EXISTS ods_cn_balance (
  symbol TEXT NOT NULL,
  report_date TEXT NOT NULL,
  indicator_name TEXT NOT NULL,
  indicator_value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, report_date, indicator_name)
);

CREATE TABLE IF NOT EXISTS ods_cn_share_structure (
  symbol TEXT NOT NULL,
  change_date TEXT NOT NULL,
  total_shares DOUBLE PRECISION,
  float_shares DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, change_date)
);
```

应用（两个库都要）：

```bash
docker exec -i warehouse-db-1 psql -U warehouse -d warehouse -v ON_ERROR_STOP=1 -q < warehouse/models/02_ods.sql
docker exec -i warehouse-db-1 psql -U warehouse -d warehouse_test -v ON_ERROR_STOP=1 -q < warehouse/models/02_ods.sql
```

验证：`docker exec warehouse-db-1 psql -U warehouse -d warehouse_test -c "\dt ods_cn_*"` 应列出 `ods_cn_balance` 与 `ods_cn_share_structure`。

**同时必须扩展两个既有测试夹具**（否则新 source 的指标会残留在测试库，导致既有测试 `test_sync_external_refreshes_indicator_dws` 因 `dws_indicator_daily` 行数变化而失败）：

`warehouse/tests/test_build_indicator.py` 的 `cleanup_indicator` 夹具，把清理范围从只有 `'crypto'` 扩为：

```python
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator
              WHERE source IN ('crypto','cn-balance','cn-daily')
            )
            """
        )
        cur.execute(
            "DELETE FROM dim_indicator WHERE source IN ('crypto','cn-balance','cn-daily')"
        )
        cur.execute("DELETE FROM ods_cn_balance WHERE sync_batch_id LIKE 'test-%'")
```

`warehouse/tests/test_sync_external.py` 的 `cleanup_external_sync` 夹具，把新表与新 source 加进去：

```python
        for table in (
            "ods_crypto_meta",
            "ods_sec_submissions",
            "ods_sec_facts",
            "ods_macro_indicators",
            "ods_cn_financials",
            "ods_cn_lhb",
            "ods_cn_balance",
            "ods_cn_share_structure",
            "ods_cn_daily_metrics",
        ):
            cur.execute(f"DELETE FROM {table} WHERE sync_batch_id LIKE 'test-extsync-%'")
        cur.execute(
            """
            DELETE FROM fact_indicator WHERE indicator_id IN (
              SELECT indicator_id FROM dim_indicator
              WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb','cn-balance','cn-daily')
            )
            """
        )
        cur.execute(
            """
            DELETE FROM dim_indicator
            WHERE source IN ('crypto','macro','sec','cn-finance','cn-lhb','cn-balance','cn-daily')
            """
        )
        cur.execute(
            """
            DELETE FROM etl_watermarks
            WHERE scope LIKE 'coingecko:%' OR scope LIKE 'sec:%'
               OR scope LIKE 'worldbank:%' OR scope LIKE 'akshare:%'
               OR scope LIKE 'cn-balance:%' OR scope LIKE 'cn-share:%'
               OR scope = 'cn-daily:metrics'
            """
        )
```

注意两点：

- `ods_cn_daily_metrics` 表要到 Task 5 才创建。**本次不要把它写进上面的 `table` 循环**（会报表不存在），Task 5 会补。同理 `test_build_indicator.py` 里对 `ods_cn_daily_metrics` 的删除语句也留到 Task 5 再加。
- `cn-daily` source 此时尚无数据，但先写进 source 列表无害。

- [ ] **Step 2: Write the failing test**

在 `warehouse/tests/test_build_indicator.py` 末尾追加：

```python
def test_build_indicators_reads_cn_balance(dsn, cleanup_indicator):
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ods_cn_balance
              (symbol, report_date, indicator_name, indicator_value, raw_payload, sync_batch_id)
            VALUES ('600519', '2026-06-30', '总资产', 309050784569.31, '{}', 'test-bi-balance')
            ON CONFLICT DO NOTHING
            """
        )
        conn.commit()

    with connect(dsn) as conn:
        affected = build_indicators(conn, "cn-balance")
        conn.commit()
    assert affected >= 1

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM fact_indicator f
            JOIN dim_indicator d ON d.indicator_id = f.indicator_id
            WHERE d.source = 'cn-balance' AND d.name = '总资产'
              AND f.ref_key = '600519' AND f.value = 309050784569.31
            """
        )
        assert cur.fetchone()[0] == 1
        cur.execute("DELETE FROM ods_cn_balance WHERE sync_batch_id = 'test-bi-balance'")
        conn.commit()
```

在 `warehouse/tests/test_sync_external.py` 末尾追加：

```python
def test_sync_balance_sheet_tolerates_single_symbol_failure(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import sina_cn
    from etl.sync_external import sync_balance_sheet

    monkeypatch.setattr(
        "etl.sync_external._a_share_universe", lambda: ["600519", "000001"]
    )

    def _fetch(code: str) -> list[dict]:
        if code == "000001":
            raise RuntimeError("network down")
        return [{"报告日": "20260630", "资产总计": 100.0}]

    monkeypatch.setattr(sina_cn, "fetch_balance_sheet", _fetch)

    with connect(dsn) as conn:
        stats = sync_balance_sheet(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    assert stats["rows"] == 1
    assert stats["failed"] == 1  # 000001 失败但不影响 600519


def test_sync_share_structure_rewinds_metrics_watermark_on_backfill(
    dsn, cleanup_external_sync, monkeypatch
):
    from etl.sources import eastmoney_cn
    from etl.sync_external import METRICS_SCOPE, set_watermark, sync_share_structure

    monkeypatch.setattr("etl.sync_external._a_share_universe", lambda: ["600519"])
    monkeypatch.setattr(
        eastmoney_cn,
        "fetch_share_structure",
        lambda _code: [
            {"变更日期": "2026-05-28", "总股本": 1250081601, "已流通股份": 1250081601}
        ],
    )

    with connect(dsn) as conn:
        set_watermark(conn, METRICS_SCOPE, "2026-09-01")
        conn.commit()

    with connect(dsn) as conn:
        sync_share_structure(conn, batch_id=f"test-extsync-{uuid.uuid4()}")
        conn.commit()

    with connect(dsn) as conn:
        # 股本变更日期早于已处理区间，水位线必须回退以重算
        assert get_watermark(conn, METRICS_SCOPE) == "2026-05-28"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_build_indicator.py tests/test_sync_external.py -q -k "balance"`

Expected: FAIL — `ImportError: cannot import name 'sync_balance_sheet'`

- [ ] **Step 4: Write minimal implementation**

在 `warehouse/etl/load_external.py` 的 `EXTERNAL_TABLES` 字典中（`cn_lhb` 之后）追加：

```python
    "cn_balance": {
        "table": "ods_cn_balance",
        "key": ["symbol", "report_date", "indicator_name"],
        "columns": [
            "symbol",
            "report_date",
            "indicator_name",
            "indicator_value",
            "raw_payload",
            "sync_batch_id",
        ],
    },
    "cn_share_structure": {
        "table": "ods_cn_share_structure",
        "key": ["symbol", "change_date"],
        "columns": [
            "symbol",
            "change_date",
            "total_shares",
            "float_shares",
            "raw_payload",
            "sync_batch_id",
        ],
    },
```

在 `warehouse/etl/build_indicator.py` 的 `_iter_rows` 中，`cn-finance` 分支之后插入：

```python
    elif source == "cn-balance":
        cur.execute(
            """
            SELECT indicator_name, symbol, report_date, indicator_value
            FROM ods_cn_balance
            """
        )
        for row in cur.fetchall():
            name = row["indicator_name"]
            symbol = row["symbol"]
            period = row["report_date"]
            value = row["indicator_value"]
            if value is None:
                continue
            yield name, name, "CNY", symbol, _parse_date(period), value
```

在 `warehouse/etl/sync_external.py` 顶部导入区加入：

```python
from etl.sources import eastmoney_cn, sina_cn
```

并在 `sync_akshare` 之后追加：

```python
METRICS_SCOPE = "cn-daily:metrics"


def _rewind_metrics_watermark(conn: Any, earliest_change: str) -> None:
    """股本回填历史日期时回退派生指标水位线，强制重算受影响区间。

    否则该区间内的市值/换手率会沿用变更前的股本，静默算错。
    """
    last = get_watermark(conn, METRICS_SCOPE)
    if last is None or earliest_change < last:
        set_watermark(conn, METRICS_SCOPE, earliest_change)


def _a_share_universe() -> list[str]:
    """全 A 股 6 位代码清单。改用 akshare 代码表而非东财快照（后者当前不可用）。"""
    import akshare  # lazy: heavy dependency

    frame = akshare.stock_info_a_code_name()
    return [str(code).strip() for code in frame["code"].tolist()]


def sync_balance_sheet(conn: Any, batch_id: str) -> dict[str, Any]:
    week = iso_week()
    rows: list[dict[str, Any]] = []
    failed = 0
    for symbol in _a_share_universe():
        scope = f"cn-balance:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        try:
            parsed = list(
                sina_cn.parse_balance_sheet(sina_cn.fetch_balance_sheet(symbol), symbol)
            )
        except Exception as exc:  # noqa: BLE001 - 单只失败不阻塞全市场
            failed += 1
            logger.warning("balance sheet failed for %s: %s", symbol, exc)
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id} for row in parsed
        )
        set_watermark(conn, scope, week)
    if rows:
        upsert_external_rows(conn, "cn_balance", rows)
        build_indicators(conn, "cn-balance")
    return {"rows": len(rows), "failed": failed}


def sync_share_structure(conn: Any, batch_id: str) -> dict[str, Any]:
    week = iso_week()
    rows: list[dict[str, Any]] = []
    failed = 0
    for symbol in _a_share_universe():
        scope = f"cn-share:{symbol}"
        if get_watermark(conn, scope) == week:
            continue
        try:
            parsed = list(
                eastmoney_cn.parse_share_structure(
                    eastmoney_cn.fetch_share_structure(symbol), symbol
                )
            )
        except Exception as exc:  # noqa: BLE001 - 单只失败不阻塞全市场
            failed += 1
            logger.warning("share structure failed for %s: %s", symbol, exc)
            continue
        rows.extend(
            {**row, "raw_payload": {}, "sync_batch_id": batch_id} for row in parsed
        )
        set_watermark(conn, scope, week)
    if rows:
        new_dates = _new_share_dates(conn, rows)
        upsert_external_rows(conn, "cn_share_structure", rows)
        if new_dates:
            _rewind_metrics_watermark(conn, min(new_dates))
    return {"rows": len(rows), "failed": failed}
```

> **修正说明（评审发现 Important 缺陷）**：本行原为 `_rewind_metrics_watermark(conn, min(row["change_date"] for row in rows))`，是**错误的**。`sync_share_structure` 每周对全市场重抓**完整变更历史**（实测仅茅台一只就返回 16 条、跨度 2001 至 2026），故 `rows` 是全市场历史，`min` 取到的是**全市场最早变更日**（≈1990），而非本次新增的日期。后果是水位线每周被打回远古日期，迫使 Task 5 每周全量重算，增量水位线形同虚设。
>
> 正确做法：先查表中已存在的 `(symbol, change_date)` 集合，与本次 `rows` 求差集，仅在差集非空时取其中最小 `change_date` 作为回退目标。

并在 `sync_external` 的 `stats` 字典中加入两个新源：

```python
    stats = {
        "coingecko": _run_source(dsn, batch_id, sync_coingecko),
        "sec": _run_source(dsn, batch_id, sync_sec),
        "worldbank": _run_source(dsn, batch_id, sync_worldbank),
        "akshare": _run_source(dsn, batch_id, sync_akshare),
        "cn-balance": _run_source(dsn, batch_id, sync_balance_sheet),
        "cn-share": _run_source(dsn, batch_id, sync_share_structure),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_build_indicator.py tests/test_sync_external.py -q`

Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add warehouse/models/02_ods.sql warehouse/etl/load_external.py warehouse/etl/build_indicator.py warehouse/etl/sync_external.py warehouse/tests/test_build_indicator.py warehouse/tests/test_sync_external.py
git commit -m "feat: 资产负债表与股本结构接入数仓管线

新增 ods_cn_balance / ods_cn_share_structure 两张贴源表与
cn-balance 指标来源，全市场采集采用 per-symbol 容错。"
```

---

### Task 5: 派生指标构建（换手率 · 总市值）

**Files:**
- Modify: `warehouse/models/02_ods.sql`（追加 `ods_cn_daily_metrics`）
- Modify: `warehouse/etl/load_external.py`（追加 `cn_daily_metrics`）
- Modify: `warehouse/etl/build_indicator.py`（追加 `cn-daily` 分支）
- Create: `warehouse/etl/build_daily_metrics.py`
- Test: `warehouse/tests/test_build_daily_metrics.py`

**Interfaces:**
- Consumes: `ods_cn_share_structure`（Task 4）、`fact_kline` / `dim_instrument`（既有）、`METRICS_SCOPE`（Task 4）
- Produces:
  - `shares_as_of(table, symbol, trade_date) -> tuple[float, float | None] | None`
  - `compute_rows(klines: Iterable[dict], table) -> Iterator[dict]` — 产出 `{"symbol", "trade_date", "close_price", "turnover_rate", "market_cap"}`
  - `build_daily_metrics(dsn: str, batch_id: str | None = None) -> dict`
  - 指标 source `cn-daily`，含 `换手率`、`总市值`

公式（已在真实数据上验证）：

```
换手率(%) = volume(手) × 10000 ÷ float_shares(股)
总市值    = close × total_shares
```

验证基准：600519 于 2026-09-21，`volume=25017` 手、`float_shares=1250081601` → `0.200123%`，与新浪 `turnover=0.0020012`（小数）一致。

水位线语义：`cn-daily:metrics` 存**下一个待处理交易日**，处理条件为 `date_key >= 水位线`（默认 `1970-01-01`）。这样股本回填时可以简单地把水位线回退到 `change_date` 即可重算。

- [ ] **Step 1: 追加 DDL 并应用到两个库**

在 `warehouse/models/02_ods.sql` **末尾追加**：

```sql
CREATE TABLE IF NOT EXISTS ods_cn_daily_metrics (
  symbol TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  close_price DOUBLE PRECISION,
  turnover_rate DOUBLE PRECISION,
  market_cap DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, trade_date)
);
```

```bash
docker exec -i warehouse-db-1 psql -U warehouse -d warehouse -v ON_ERROR_STOP=1 -q < warehouse/models/02_ods.sql
docker exec -i warehouse-db-1 psql -U warehouse -d warehouse_test -v ON_ERROR_STOP=1 -q < warehouse/models/02_ods.sql
```

**补齐 Task 4 预留的夹具**：现在 `ods_cn_daily_metrics` 已存在，把它的清理补进两个夹具：

- `warehouse/tests/test_sync_external.py` 的 `cleanup_external_sync`：在 `table` 元组中加入 `"ods_cn_daily_metrics"`。
- `warehouse/tests/test_build_indicator.py` 的 `cleanup_indicator`：加入 `cur.execute("DELETE FROM ods_cn_daily_metrics WHERE sync_batch_id LIKE 'test-%'")`。

- [ ] **Step 2: Write the failing test**

创建 `warehouse/tests/test_build_daily_metrics.py`：

```python
"""Daily A-share derived metrics tests."""
from __future__ import annotations

import pytest

from etl.build_daily_metrics import compute_rows, shares_as_of


TABLE = {
    "600519": (
        ["2025-09-01", "2026-05-28"],
        [(1252270215.0, 1252270215.0), (1250081601.0, 1250081601.0)],
    )
}

KLINES = [
    {"symbol": "600519", "trade_date": "2026-09-21", "close": 1252.57, "volume": 25017.0}
]


def test_shares_as_of_picks_latest_change_not_after_trade_date():
    assert shares_as_of(TABLE, "600519", "2026-06-30") == (1250081601.0, 1250081601.0)
    assert shares_as_of(TABLE, "600519", "2026-01-15") == (1252270215.0, 1252270215.0)


def test_shares_as_of_returns_none_before_first_change():
    assert shares_as_of(TABLE, "600519", "2025-01-01") is None


def test_shares_as_of_returns_none_for_unknown_symbol():
    assert shares_as_of(TABLE, "000001", "2026-09-21") is None


def test_compute_rows_turnover_matches_sina_reference():
    """600519 于 2026-09-21：新浪 turnover 实测 0.0020012（小数）= 0.20012%。"""
    rows = list(compute_rows(KLINES, TABLE))
    assert len(rows) == 1
    assert rows[0]["turnover_rate"] == pytest.approx(0.20012, rel=1e-3)
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)


def test_compute_rows_skips_symbol_without_shares():
    klines = [{"symbol": "000001", "trade_date": "2026-09-21", "close": 10.0, "volume": 100.0}]
    assert list(compute_rows(klines, TABLE)) == []


def test_compute_rows_leaves_turnover_null_when_float_shares_missing():
    table = {"600519": (["2026-05-28"], [(1250081601.0, None)])}
    rows = list(compute_rows(KLINES, table))
    assert rows[0]["turnover_rate"] is None
    assert rows[0]["market_cap"] == pytest.approx(1252.57 * 1250081601.0)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_build_daily_metrics.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'etl.build_daily_metrics'`

- [ ] **Step 4: Write minimal implementation**

在 `warehouse/etl/load_external.py` 的 `EXTERNAL_TABLES` 中追加：

```python
    "cn_daily_metrics": {
        "table": "ods_cn_daily_metrics",
        "key": ["symbol", "trade_date"],
        "columns": [
            "symbol",
            "trade_date",
            "close_price",
            "turnover_rate",
            "market_cap",
            "raw_payload",
            "sync_batch_id",
        ],
    },
```

在 `warehouse/etl/build_indicator.py` 的 `_iter_rows` 中追加：

```python
    elif source == "cn-daily":
        cur.execute(
            """
            SELECT symbol, trade_date, turnover_rate, market_cap
            FROM ods_cn_daily_metrics
            """
        )
        for row in cur.fetchall():
            symbol = row["symbol"]
            trade_date = row["trade_date"]
            for source_key, name, unit, value in (
                ("turnover_rate", "换手率", "%", row["turnover_rate"]),
                ("market_cap", "总市值", "CNY", row["market_cap"]),
            ):
                if value is None:
                    continue
                yield source_key, name, unit, symbol, _parse_date(trade_date), value
```

创建 `warehouse/etl/build_daily_metrics.py`：

```python
"""Derive daily A-share metrics (turnover rate, market cap) from klines."""
from __future__ import annotations

import bisect
import os
from datetime import date, timedelta
from typing import Any, Iterable, Iterator

from psycopg.rows import dict_row

from etl.build_indicator import build_indicators
from etl.db import connect
from etl.load_external import upsert_external_rows
from etl.sync_external import METRICS_SCOPE, get_watermark, set_watermark

DEFAULT_DSN = "postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
_EPOCH = "1970-01-01"


def load_share_structures(conn: Any) -> dict[str, tuple[list[str], list[tuple[float, float | None]]]]:
    """symbol -> (升序变更日期, [(总股本, 流通股本), ...])"""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT symbol, change_date, total_shares, float_shares
            FROM ods_cn_share_structure
            ORDER BY symbol, change_date
            """
        )
        table: dict[str, tuple[list[str], list[tuple[float, float | None]]]] = {}
        for row in cur.fetchall():
            dates, values = table.setdefault(row["symbol"], ([], []))
            dates.append(row["change_date"])
            values.append((row["total_shares"], row["float_shares"]))
        return table


def shares_as_of(
    table: dict[str, tuple[list[str], list[tuple[float, float | None]]]],
    symbol: str,
    trade_date: str,
) -> tuple[float, float | None] | None:
    """取 change_date <= trade_date 的最新股本记录；无记录返回 None。"""
    entry = table.get(symbol)
    if entry is None:
        return None
    dates, values = entry
    index = bisect.bisect_right(dates, trade_date) - 1
    if index < 0:
        return None
    return values[index]


def compute_rows(
    klines: Iterable[dict[str, Any]],
    table: dict[str, tuple[list[str], list[tuple[float, float | None]]]],
) -> Iterator[dict[str, Any]]:
    for row in klines:
        shares = shares_as_of(table, row["symbol"], row["trade_date"])
        if shares is None:
            continue
        total_shares, float_shares = shares
        market_cap = row["close"] * total_shares if total_shares else None
        turnover_rate = (
            row["volume"] * 10000.0 / float_shares if float_shares else None
        )
        yield {
            "symbol": row["symbol"],
            "trade_date": row["trade_date"],
            "close_price": row["close"],
            "turnover_rate": turnover_rate,
            "market_cap": market_cap,
        }


def _fetch_klines(conn: Any, since: str) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT i.symbol, k.date_key::text AS trade_date, k.close, k.volume
            FROM fact_kline k
            JOIN dim_instrument i ON i.instrument_id = k.instrument_id
            WHERE k.market_id = 'a-share' AND k.period = 'd' AND k.date_key >= %s
            ORDER BY k.date_key, i.symbol
            """,
            (since,),
        )
        return cur.fetchall()


def build_daily_metrics(dsn: str, batch_id: str | None = None) -> dict[str, Any]:
    batch_id = batch_id or f"daily-metrics-{date.today().isoformat()}"
    with connect(dsn) as conn:
        since = get_watermark(conn, METRICS_SCOPE) or _EPOCH
        klines = _fetch_klines(conn, since)
        if not klines:
            return {"rows": 0, "through": None}
        table = load_share_structures(conn)
        rows = [
            {**row, "raw_payload": {}, "sync_batch_id": batch_id}
            for row in compute_rows(klines, table)
        ]
        if rows:
            upsert_external_rows(conn, "cn_daily_metrics", rows)
            build_indicators(conn, "cn-daily")
        last_date = max(row["trade_date"] for row in klines)
        next_date = (date.fromisoformat(last_date) + timedelta(days=1)).isoformat()
        set_watermark(conn, METRICS_SCOPE, next_date)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW dws_indicator_daily")
        conn.commit()
    return {"rows": len(rows), "through": last_date}


def main() -> None:
    dsn = os.environ.get("WAREHOUSE_DSN", DEFAULT_DSN)
    print(build_daily_metrics(dsn))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_build_daily_metrics.py -q`

Expected: `6 passed`

- [ ] **Step 6: Run full suite**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests -q`

Expected: 全部通过，无回归

- [ ] **Step 7: Commit**

```bash
git add warehouse/models/02_ods.sql warehouse/etl/load_external.py warehouse/etl/build_indicator.py warehouse/etl/build_daily_metrics.py warehouse/tests/test_build_daily_metrics.py
git commit -m "feat: 由 K 线与股本派生换手率与总市值

换手率 = volume(手) × 10000 ÷ 流通股本，总市值 = close × 总股本，
按 change_date <= trade_date 取历史股本，避免用未来股本回填。"
```

---

### Task 6: 端到端真实数据验证

**Files:**
- 无新增；本任务只做验证，若发现缺陷则回到对应 Task 修复

**Interfaces:**
- Consumes: Task 1-5 的全部产出
- Produces: 验收结论（对应 spec 第 9 节 6 条标准）

- [ ] **Step 1: 全量同步财务源**

Run:

```bash
cd warehouse && WAREHOUSE_DSN="postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse" /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m etl.sync_external
```

Expected: `cn-balance` 与 `cn-share` 均为 `status: ok`；`cn-balance` 行数达到 1 万量级（5565 只 × 若干报告期）。其余源的状态不影响本任务验收（coingecko 已知会超时）。

- [ ] **Step 2: 构建派生指标**

Run:

```bash
cd warehouse && WAREHOUSE_DSN="postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse" /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m etl.build_daily_metrics
```

Expected: 输出 `{'rows': <大数>, 'through': '<最新交易日>'}`

- [ ] **Step 3: 核对落库表**

Run:

```bash
docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "
SELECT 'ods_cn_balance' t, count(*) FROM ods_cn_balance
UNION ALL SELECT 'ods_cn_share_structure', count(*) FROM ods_cn_share_structure
UNION ALL SELECT 'ods_cn_daily_metrics', count(*) FROM ods_cn_daily_metrics
ORDER BY 1;"
```

Expected: 三表均有非零行数

- [ ] **Step 4: 核对五个指标进入通用模型**

Run:

```bash
docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "
SELECT d.source, d.name, count(*) AS rows
FROM fact_indicator f JOIN dim_indicator d ON d.indicator_id = f.indicator_id
WHERE d.source IN ('cn-balance','cn-daily')
GROUP BY 1,2 ORDER BY 1,2;"
```

Expected: 5 行，分别为 `cn-balance` 的 总资产/净资产(归母)/净资产(合计) 与 `cn-daily` 的 换手率/总市值

- [ ] **Step 5: 核对数值与源一致**

Run:

```bash
docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "
SELECT d.name, f.ref_key, f.as_of_date, f.value
FROM fact_indicator f JOIN dim_indicator d ON d.indicator_id = f.indicator_id
WHERE d.source = 'cn-balance' AND f.ref_key = '600519'
ORDER BY f.as_of_date DESC, d.name LIMIT 3;"
```

Expected: 总资产约 `309050784569`（3090 亿）、净资产(归母) 约 `251253594419`（2512 亿）

再核对总市值：

```bash
docker exec warehouse-db-1 psql -U warehouse -d warehouse -c "
SELECT d.name, f.ref_key, f.as_of_date, f.value
FROM fact_indicator f JOIN dim_indicator d ON d.indicator_id = f.indicator_id
WHERE d.source = 'cn-daily' AND f.ref_key = '600519' AND d.name IN ('总市值','换手率')
ORDER BY f.as_of_date DESC LIMIT 4;"
```

Expected: 总市值约 `1.5e12` 量级（1.5 万亿），换手率在 `0.05 ~ 2` 的百分数量级（不要出现 0.0002 或 20 这类量级错误）

- [ ] **Step 6: 验证水位线幂等性**

再跑一次 Step 1，Expected: `cn-balance` 与 `cn-share` 的 `rows` 均为 0（同一周内跳过）

再跑一次 Step 2，Expected: `rows` 为 0（已处理到最新交易日）

- [ ] **Step 7: 全量测试套件**

Run: `cd warehouse && WAREHOUSE_DSN="postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test" /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests -q`

Expected: 全部通过，无回归

- [ ] **Step 8: 记录验收结果**

若全部符合，在 spec 的验收标准处以 `- [x]` 标记完成；若有偏差，回到对应 Task 修复后重跑本任务。

```bash
git add docs/superpowers/specs/2026-09-22-cn-fundamentals-pipeline-design.md
git commit -m "docs: 记录 A 股基本面采集子项目 1 验收结果"
```

---

## 自审记录

**Spec 覆盖检查：**

| Spec 要求 | 对应 Task |
|---|---|
| 新增新浪资产负债表源 | Task 1 |
| 新增东财股本结构源 | Task 2 |
| 水位线修复（含 sec/worldbank/akshare） | Task 3 |
| 3 张 ODS 表 | Task 4（2 张）、Task 5（1 张） |
| cn-balance / cn-daily 指标映射 | Task 4、Task 5 |
| 换手率公式与单位约定 | Task 5 |
| 总市值与 `change_date <= trade_date` 约束 | Task 5 |
| 标的清单（`stock_info_a_code_name`）与前缀规则 | Task 4（`_a_share_universe`）、Task 1（`sina_symbol`） |
| per-symbol 容错 | Task 4 |
| 增量策略与 DWS 刷新 | Task 5 |
| 测试用真实响应形状 | Task 1、2、5 的 fixture |
| 6 条验收标准 | Task 6 |

**自审中修掉的两处问题（原本被我标为"缺口"，已直接修复而非留作备注）：**

1. **股本回填的水位线回退**（spec 第 4.3 节的硬要求）：已在 Task 4 加入 `_rewind_metrics_watermark()` 及配套测试 `test_sync_share_structure_rewinds_metrics_watermark_on_backfill`。该测试只依赖 `etl_watermarks`，不需要 `fact_kline` 历史数据，因此可以在 Task 4 内直接验证。
2. **`cn-daily` 的 unit 混淆**：初稿对换手率与总市值统一填 `"CNY"`，对换手率是错的。已改为逐指标带上 unit（`换手率 → "%"`、`总市值 → "CNY"`）。

**执行时仍需留意：**

- **`cn-daily` 只有 A 股**：`_fetch_klines` 按 `market_id = 'a-share'` 过滤，美股/港股/加密不产出换手率与总市值。这是 spec 明确的范围限定，不是缺陷。
- **首次全市场采集耗时约 65 分钟**：Task 6 Step 1 会真实遍历 5565 只标的，务必用充足超时，不要在超时后误判为失败。
- **coingecko 在 Task 6 会报 error**：已知网络超时，与本次改动无关，只要 `cn-balance` / `cn-share` 为 `ok` 即可继续验收。
