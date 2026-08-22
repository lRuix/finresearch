# 全标的投研平台四层架构深化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 FastAPI 单体重构为展示层、应用层、领域层、基础设施层四层端口适配器架构，API 契约与前端保持不变。

**Architecture:** 依赖倒置的分层单体。端口定义在 `application/ports.py`，`infrastructure/` 实现端口，`domain/` 保持纯逻辑，`presentation/` 只做参数校验与响应格式，`core/` 作为限期兼容层。

**Tech Stack:** FastAPI + Pydantic + Python 标准库 `sqlite3` + pytest；前端 React 不参与改动。

---

## 执行前置检查

- [ ] 保留工作区未提交改动：实施前先 `git status --short`，若存在与本计划无关的用户改动，不要覆盖，必要时先让用户确认是否提交。
- [ ] 基线测试通过：`cd backend && .venv/bin/python -m pytest -q`，预期全部 PASS。
- [ ] git 写入 `.git` 需要提权：本仓库沙箱对 `.git` 只读，执行 `git add` / `git commit` 时使用 `require_escalated`，并给出中文 justification。

---

## Phase 0: 领域层落位

### Task 0.1: 创建领域值对象

**Files:**
- Create: `backend/domain/__init__.py`
- Create: `backend/domain/models.py`
- Test: `backend/tests/unit/test_domain_models.py`

- [ ] **Step 1: 写失败测试**

```python
"""Domain value object tests."""
from dataclasses import FrozenInstanceError

import pytest

from domain.models import Instrument, KlineRow


def test_instrument_defaults():
    item = Instrument(market="us", symbol="AAPL", name="Apple", currency="USD")
    assert item.sector is None
    assert item.base_risk is None
    assert item.liquidity is None


def test_instrument_is_frozen():
    item = Instrument(market="us", symbol="AAPL", name="Apple", currency="USD")
    with pytest.raises(FrozenInstanceError):
        item.name = "Other"


def test_kline_row_fields():
    row = KlineRow(time="2026-08-23", open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
    assert row.close == 1.5
    assert row.volume == 100
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_models.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'domain'`

- [ ] **Step 3: 最小实现**

`backend/domain/__init__.py`:

```python
"""Pure domain layer: value objects, indicators, valuation and algorithms."""
```

`backend/domain/models.py`:

```python
"""Domain value objects shared by application and algorithm layers."""
from __future__ import annotations

from dataclasses import dataclass


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

同时创建 `backend/tests/unit/__init__.py`（空文件）。

- [ ] **Step 4: 确认测试通过**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_models.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/domain backend/tests/unit
git commit -m "feat: 新增领域层 Instrument/KlineRow 值对象"
```

### Task 0.2: 迁移 indicators 到领域层

**Files:**
- Create: `backend/domain/indicators.py`
- Test: `backend/tests/unit/test_domain_indicators.py`

- [ ] **Step 1: 复制现有实现**

Run: `cp backend/core/indicators.py backend/domain/indicators.py`
说明：`core/indicators.py` 是纯函数模块，不 import 网络层，原样复制即可；`core/indicators.py` 保留为兼容层，直到 Phase 5 清理。

- [ ] **Step 2: 写领域层指标测试**

`backend/tests/unit/test_domain_indicators.py`:

```python
"""Domain indicators sanity tests."""
from domain.indicators import analyze, rsi, sma


def test_sma_requires_enough_values():
    assert sma([1.0, 2.0], 5) is None
    assert sma([1.0, 2.0, 3.0], 2) == 2.5


def test_rsi_basic():
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
              11.0, 12.0, 13.0, 14.0, 15.0]
    assert rsi(closes, 14) == 100.0


def test_analyze_requires_two_rows():
    result = analyze([{"close": 1.0}])
    assert result["error"] == "insufficient kline data"
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_indicators.py -q`
Expected: PASS（3 passed）

- [ ] **Step 4: 回归旧测试**

Run: `cd backend && .venv/bin/python -m pytest -q -q`
Expected: 现有测试继续 PASS（core/indicators 未被改动）

- [ ] **Step 5: 提交**

```bash
git add backend/domain/indicators.py backend/tests/unit/test_domain_indicators.py
git commit -m "feat: 迁移技术指标实现到领域层"
```

### Task 0.3: 迁移 valuation 到领域层并去掉 providers 依赖

**Files:**
- Create: `backend/domain/valuation/__init__.py`
- Create: `backend/domain/valuation/currency.py`
- Create: `backend/domain/valuation/constraints.py`
- Create: `backend/domain/valuation/metrics.py`
- Test: `backend/tests/unit/test_domain_valuation.py`

- [ ] **Step 1: 复制 constraints 与 metrics**

Run: `cp backend/core/valuation/constraints.py backend/domain/valuation/constraints.py`
Run: `cp backend/core/valuation/metrics.py backend/domain/valuation/metrics.py`

`backend/domain/valuation/__init__.py`:

```python
"""Pure valuation logic."""
```

- [ ] **Step 2: 写纯函数版 currency**

`backend/domain/valuation/currency.py`:

```python
"""Unified RMB valuation, pure functions only.

The real-time fx rate is injected by application services via FxRateProvider;
this module never imports providers or makes network requests.
"""
from __future__ import annotations


def to_rmb_returns(returns: list[float], fx_change: float) -> list[float]:
    factor = 1 + fx_change
    return [(1 + r) * factor - 1 for r in returns]


def to_rmb_closes(closes: list[float], fx_rate: float) -> list[float]:
    return [c * fx_rate for c in closes]


STATIC_FX_RATES = {
    "CNY": 1.0,
    "USD": 7.18,
    "HKD": 0.92,
    "KRW": 0.0053,
    "USDT": 7.18,
    "MULTI": 1.0,
}


def static_reference_fx_rate(currency: str) -> float:
    return STATIC_FX_RATES.get(currency, 1.0)
```

- [ ] **Step 3: 写领域估值测试**

`backend/tests/unit/test_domain_valuation.py`:

```python
"""Domain valuation purity and behavior tests."""
import inspect

from domain.valuation import currency, metrics


def test_to_rmb_closes():
    assert currency.to_rmb_closes([10.0, 11.0], 7.18) == [71.8, 78.98]


def test_currency_module_has_no_provider_import():
    source = inspect.getsource(currency)
    assert "providers" not in source


def test_calmar_ratio():
    closes = [100.0, 110.0, 105.0, 120.0, 118.0]
    calmar = metrics.calmar_ratio(closes)
    assert calmar is not None
    assert calmar > 0
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_valuation.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/domain/valuation backend/tests/unit/test_domain_valuation.py
git commit -m "refactor: 估值逻辑迁移到领域层并去除 providers 依赖"
```

### Task 0.4: 迁移 algorithms 到领域层

**Files:**
- Create: `backend/domain/algorithms/`（复制自 `backend/core/algorithms/`）
- Test: `backend/tests/unit/test_domain_algorithms.py`

- [ ] **Step 1: 复制算法包**

Run: `cp -R backend/core/algorithms backend/domain/algorithms`

- [ ] **Step 2: 替换包内绝对导入**

Run:

```bash
cd backend
rg -l "core\.algorithms|core\.indicators" domain/algorithms | while read -r f; do
  sed -i '' -e 's/from core\.algorithms/from domain.algorithms/g' \
            -e 's/import core\.algorithms/import domain.algorithms/g' \
            -e 's/from core\.indicators/from domain.indicators/g' "$f"
done
rg -n "core\.algorithms|core\.indicators" domain/algorithms || true
```

Expected: 第二条 `rg` 无输出。

- [ ] **Step 3: 写领域算法测试**

`backend/tests/unit/test_domain_algorithms.py`:

```python
"""Domain algorithms smoke tests."""
from domain.algorithms.config import build_engine
from domain.algorithms.context import AnalysisContext


def test_build_engine_and_score():
    engine = build_engine()
    ctx = AnalysisContext(
        symbol="AAPL",
        market="us",
        currency="USD",
        klines=[
            {"time": f"2026-08-{i:02d}", "close": 100.0 + i}
            for i in range(1, 61)
        ],
        macro_bias=58.0,
        news_sentiment=0.1,
        fx_rate=7.18,
        horizon="short",
    )
    factor_scores = {factor.name: factor.score(ctx)["score"] for factor in engine.factors}
    combined = engine.combine(factor_scores, engine.sentiment.analyze(ctx))
    assert 0 <= combined["total_score"] <= 100
```

- [ ] **Step 4: 运行测试并回归**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_algorithms.py -q`
Expected: PASS

Run: `cd backend && .venv/bin/python -m pytest -q -q`
Expected: 现有测试（仍指向 core.algorithms）继续 PASS

- [ ] **Step 5: 提交**

```bash
git add backend/domain/algorithms backend/tests/unit/test_domain_algorithms.py
git commit -m "refactor: 算法层迁移到领域层并保持 core 兼容"
```

### Task 0.5: 迁移静态标的池到领域层

**Files:**
- Create: `backend/domain/universe_data.py`
- Test: `backend/tests/unit/test_domain_universe.py`

- [ ] **Step 1: 复制静态数据与查询函数**

Run: `cp backend/core/universe.py backend/domain/universe_data.py`

说明：`universe.py` 只有静态数据与 `find_symbol` / `universe_for`，无外部依赖，原样复制即可；`core/universe.py` 保留为兼容层。

- [ ] **Step 2: 写领域标的池测试**

`backend/tests/unit/test_domain_universe.py`:

```python
"""Domain universe data tests."""
from domain.universe_data import MARKETS, find_symbol, universe_for


def test_markets_cover_expected_ids():
    ids = {m["id"] for m in MARKETS}
    assert {"a-share", "us", "kr", "hk", "fund", "fx", "crypto"} <= ids


def test_find_symbol_and_universe_for():
    item = find_symbol("us", "AAPL")
    assert item is not None
    assert item["market"] == "us"
    assert universe_for("us")
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_domain_universe.py -q`
Expected: PASS（2 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/domain/universe_data.py backend/tests/unit/test_domain_universe.py
git commit -m "refactor: 静态标的池迁移到领域层"
```

---

## Phase 1: 端口、仓库与同步

### Task 1.1: 定义应用端口与配置

**Files:**
- Create: `backend/application/__init__.py`
- Create: `backend/application/ports.py`
- Create: `backend/application/config.py`
- Test: `backend/tests/unit/test_ports_config.py`

- [ ] **Step 1: 写测试**

`backend/tests/unit/test_ports_config.py`:

```python
"""Ports and config import tests."""
from pathlib import Path

from application.config import AppConfig
from application.ports import (
    FxRateProvider,
    MacroNewsProvider,
    MarketDataSource,
    MarketDataRepository,
)


def test_ports_importable():
    assert MarketDataRepository is not None
    assert MarketDataSource is not None
    assert FxRateProvider is not None
    assert MacroNewsProvider is not None


def test_default_config_uses_backend_data_dir():
    cfg = AppConfig()
    assert str(cfg.db_path).endswith("backend/data/research.db")
    assert isinstance(cfg.db_path, Path)
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_ports_config.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'application'`

- [ ] **Step 3: 实现**

`backend/application/__init__.py`:

```python
"""Application orchestration layer."""
```

`backend/application/ports.py`:

```python
"""Application ports.

Infrastructure implements these protocols; application services depend only
on them so repository, datasource and fx providers stay replaceable.
"""
from __future__ import annotations

from typing import Protocol

from domain.models import Instrument, KlineRow


class MarketDataRepository(Protocol):
    def upsert_instruments(self, items: list[Instrument]) -> None: ...
    def upsert_klines(self, market: str, symbol: str, period: str,
                      rows: list[KlineRow]) -> None: ...
    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None) -> list[KlineRow]: ...
    def get_watermark(self, market: str, symbol: str, period: str) -> str | None: ...
    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None: ...
    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None: ...
    def get_snapshot(self, date: str, market: str) -> list[dict]: ...
    def save_evaluation(self, evaluated_on: str, market: str, symbol: str,
                        score: float, payload: dict) -> None: ...
    def get_evaluation(self, evaluated_on: str, market: str, symbol: str) -> dict | None: ...


class MarketDataSource(Protocol):
    def list_instruments(self, market: str, top_n: int) -> list[Instrument]: ...
    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None,
                   limit: int = 180) -> list[KlineRow]: ...
    def get_klines_with_source(self, market: str, symbol: str, period: str,
                               start: str | None = None, end: str | None = None,
                               limit: int = 180) -> tuple[list[KlineRow], str]: ...
    def get_live_fx_rates(self) -> dict[str, float] | None: ...


class FxRateProvider(Protocol):
    def reference_fx_rate(self, currency: str) -> float: ...


class MacroNewsProvider(Protocol):
    def market_bias(self, market: str) -> dict | None: ...
    def macro_score(self, market: str) -> float: ...
    def news_items(self, market: str) -> list[dict]: ...
```

`backend/application/config.py`:

```python
"""Application configuration."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "research.db"


@dataclass(frozen=True)
class AppConfig:
    db_path: Path = DEFAULT_DB_PATH
    cache_ttl_seconds: int = 300
    breaker_seconds: int = 120
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_ports_config.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/application backend/tests/unit/test_ports_config.py
git commit -m "feat: 新增应用层端口与应用配置"
```

### Task 1.2: 实现 SqliteMarketDataRepository（TDD）

**Files:**
- Create: `backend/infrastructure/__init__.py`
- Create: `backend/infrastructure/repository/__init__.py`
- Create: `backend/infrastructure/repository/sqlite.py`
- Test: `backend/tests/unit/test_repository.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_repository.py`:

```python
"""SQLite repository tests using a temporary database file."""
from domain.models import Instrument, KlineRow
from infrastructure.repository.sqlite import SqliteMarketDataRepository


def _rows():
    return [
        KlineRow("2026-08-20", 1.0, 2.0, 0.5, 1.5, 100),
        KlineRow("2026-08-21", 1.5, 2.5, 1.2, 2.2, 120),
    ]


def test_upsert_and_read_klines(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    rows = repo.get_klines("us", "AAPL", "d")
    assert [r.time for r in rows] == ["2026-08-20", "2026-08-21"]
    assert rows[1].close == 2.2


def test_upsert_replaces_same_key(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    repo.upsert_klines("us", "AAPL", "d", [
        KlineRow("2026-08-21", 1.5, 2.5, 1.2, 9.9, 120),
    ])
    rows = repo.get_klines("us", "AAPL", "d")
    assert len(rows) == 2
    assert rows[1].close == 9.9


def test_get_klines_with_range(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_klines("us", "AAPL", "d", _rows())
    rows = repo.get_klines("us", "AAPL", "d", start="2026-08-21")
    assert [r.time for r in rows] == ["2026-08-21"]


def test_watermark_progress(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    assert repo.get_watermark("us", "AAPL", "d") is None
    repo.set_watermark("us", "AAPL", "d", "2026-08-21")
    assert repo.get_watermark("us", "AAPL", "d") == "2026-08-21"


def test_snapshot_upsert_and_read(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.upsert_snapshot("2026-08-23", "us", [
        {"symbol": "AAPL", "name": "Apple", "turnover": 1e9, "market_cap": 3e12},
        {"symbol": "MSFT", "name": "Microsoft", "turnover": 8e8, "market_cap": 3e12},
    ])
    items = repo.get_snapshot("2026-08-23", "us")
    assert [item["symbol"] for item in items] == ["AAPL", "MSFT"]


def test_evaluation_same_day_replace(tmp_path):
    repo = SqliteMarketDataRepository(tmp_path / "research.db")
    repo.save_evaluation("2026-08-23", "us", "AAPL", 80.0, {"score": 80.0})
    payload = repo.get_evaluation("2026-08-23", "us", "AAPL")
    assert payload == {"score": 80.0}
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_repository.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现仓库**

`backend/infrastructure/__init__.py` 与 `backend/infrastructure/repository/__init__.py`：空文件。

`backend/infrastructure/repository/sqlite.py`:

```python
"""SQLite implementation of MarketDataRepository."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from domain.models import Instrument, KlineRow


_SCHEMA = """
CREATE TABLE IF NOT EXISTS instruments (
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

CREATE TABLE IF NOT EXISTS klines (
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

CREATE TABLE IF NOT EXISTS market_snapshots (
  date TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL,
  turnover REAL,
  market_cap REAL,
  rank INTEGER NOT NULL,
  PRIMARY KEY (date, market, symbol)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_date_market
  ON market_snapshots(date, market);

CREATE TABLE IF NOT EXISTS evaluations (
  evaluated_on TEXT NOT NULL,
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  score REAL NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (evaluated_on, market, symbol)
);

CREATE TABLE IF NOT EXISTS sync_watermarks (
  market TEXT NOT NULL,
  symbol TEXT NOT NULL,
  period TEXT NOT NULL,
  as_of TEXT NOT NULL,
  PRIMARY KEY (market, symbol, period)
);
"""


class SqliteMarketDataRepository:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def upsert_instruments(self, items: list[Instrument]) -> None:
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO instruments
                  (market, symbol, name, currency, sector, base_risk, liquidity, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.market, item.symbol, item.name, item.currency,
                        item.sector, item.base_risk, item.liquidity,
                        item.symbol,
                    )
                    for item in items
                ],
            )
            conn.commit()

    def upsert_klines(self, market: str, symbol: str, period: str,
                      rows: list[KlineRow]) -> None:
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO klines
                  (market, symbol, period, time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (market, symbol, period, row.time, row.open, row.high,
                     row.low, row.close, row.volume)
                    for row in rows
                ],
            )
            conn.commit()

    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None) -> list[KlineRow]:
        sql = """
            SELECT time, open, high, low, close, volume FROM klines
            WHERE market = ? AND symbol = ? AND period = ?
        """
        params = [market, symbol, period]
        if start is not None:
            sql += " AND time >= ?"
            params.append(start)
        if end is not None:
            sql += " AND time <= ?"
            params.append(end)
        sql += " ORDER BY time ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [KlineRow(**dict(row)) for row in rows]

    def get_watermark(self, market: str, symbol: str, period: str) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT as_of FROM sync_watermarks WHERE market = ? AND symbol = ? AND period = ?",
                (market, symbol, period),
            ).fetchone()
        return row["as_of"] if row else None

    def set_watermark(self, market: str, symbol: str, period: str, as_of: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sync_watermarks
                  (market, symbol, period, as_of)
                VALUES (?, ?, ?, ?)
                """,
                (market, symbol, period, as_of),
            )
            conn.commit()

    def upsert_snapshot(self, date: str, market: str, items: list[dict]) -> None:
        with self._lock, self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO market_snapshots
                  (date, market, symbol, name, turnover, market_cap, rank)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        date, market, item["symbol"], item.get("name", item["symbol"]),
                        item.get("turnover"), item.get("market_cap"), rank,
                    )
                    for rank, item in enumerate(items, start=1)
                ],
            )
            conn.commit()

    def get_snapshot(self, date: str, market: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, name, turnover, market_cap, rank
                FROM market_snapshots
                WHERE date = ? AND market = ?
                ORDER BY rank ASC
                """,
                (date, market),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_evaluation(self, evaluated_on: str, market: str, symbol: str,
                        score: float, payload: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluations
                  (evaluated_on, market, symbol, score, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (evaluated_on, market, symbol, score, json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()

    def get_evaluation(self, evaluated_on: str, market: str, symbol: str) -> dict | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM evaluations
                WHERE evaluated_on = ? AND market = ? AND symbol = ?
                """,
                (evaluated_on, market, symbol),
            ).fetchone()
        return json.loads(row["payload"]) if row else None
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_repository.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/infrastructure backend/tests/unit/test_repository.py
git commit -m "feat: 实现 SQLite 市场数据仓库"
```

### Task 1.3: 实现 SyncService（TDD）

**Files:**
- Create: `backend/application/services/__init__.py`
- Create: `backend/application/services/sync_service.py`
- Test: `backend/tests/unit/test_sync_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_sync_service.py`:

```python
"""SyncService tests with in-memory repository and fake datasource."""
from domain.models import KlineRow
from application.services.sync_service import SyncService


class FakeRepository:
    def __init__(self):
        self.upserted = []
        self.watermarks = {}

    def get_watermark(self, market, symbol, period):
        return self.watermarks.get((market, symbol, period))

    def set_watermark(self, market, symbol, period, as_of):
        self.watermarks[(market, symbol, period)] = as_of

    def upsert_klines(self, market, symbol, period, rows):
        self.upserted.append((market, symbol, period, rows))


class FakeDatasource:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error

    def get_klines_with_source(self, market, symbol, period,
                               start=None, end=None, limit=180):
        if self.error:
            raise self.error
        return self.rows, "live"

    def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
        rows, _ = self.get_klines_with_source(market, symbol, period, start, end, limit)
        return rows


def test_sync_writes_rows_and_advances_watermark():
    repo = FakeRepository()
    rows = [
        KlineRow("2026-08-22", 1, 2, 0.5, 1.5, 100),
        KlineRow("2026-08-23", 1.5, 2.5, 1.2, 2.2, 120),
    ]
    service = SyncService(repo, FakeDatasource(rows=rows))
    result_rows, source = service.sync("us", "AAPL", "d")
    assert result_rows == rows
    assert source == "live"
    assert repo.upserted == [("us", "AAPL", "d", rows)]
    assert repo.watermarks[("us", "AAPL", "d")] == "2026-08-23"


def test_sync_does_not_advance_on_failure():
    repo = FakeRepository()
    service = SyncService(repo, FakeDatasource(error=RuntimeError("upstream down")))
    try:
        service.sync("us", "AAPL", "d")
    except RuntimeError:
        pass
    assert repo.upserted == []
    assert repo.watermarks == {}


def test_sync_uses_existing_watermark_as_start():
    repo = FakeRepository()
    repo.watermarks[("us", "AAPL", "d")] = "2026-08-22"
    captured = {}

    class RecordingDatasource:
        def get_klines_with_source(self, market, symbol, period,
                                   start=None, end=None, limit=180):
            captured["start"] = start
            return [], "mock"

        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            rows, source = self.get_klines_with_source(market, symbol, period, start, end, limit)
            return rows

    SyncService(repo, RecordingDatasource()).sync("us", "AAPL", "d")
    assert captured["start"] == "2026-08-22"
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_sync_service.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 SyncService**

`backend/application/services/__init__.py`：空文件。

`backend/application/services/sync_service.py`:

```python
"""Sync orchestration: fill data gaps through repository + datasource."""
from __future__ import annotations

from application.ports import MarketDataSource, MarketDataRepository


class SyncService:
    def __init__(self, repository: MarketDataRepository,
                 datasource: MarketDataSource):
        self._repository = repository
        self._datasource = datasource

    def sync(self, market: str, symbol: str, period: str,
             start: str | None = None, end: str | None = None) -> tuple[list, str]:
        watermark = self._repository.get_watermark(market, symbol, period)
        gap_start = start
        if watermark and (gap_start is None or watermark > gap_start):
            gap_start = watermark
        rows, source = self._datasource.get_klines_with_source(
            market, symbol, period, start=gap_start, end=end, limit=1000,
        )
        if rows:
            self._repository.upsert_klines(market, symbol, period, rows)
            self._repository.set_watermark(market, symbol, period, rows[-1].time)
        return rows, source
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_sync_service.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/application/services backend/tests/unit/test_sync_service.py
git commit -m "feat: 新增增量同步服务并用水位线控制缺口拉取"
```

---

## Phase 2: 数据源适配器

### Task 2.1: ProviderDataSource 与 FxRateProvider 适配器

**Files:**
- Create: `backend/infrastructure/datasources/__init__.py`
- Create: `backend/infrastructure/datasources/provider_datasource.py`
- Test: `backend/tests/unit/test_provider_datasource.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_provider_datasource.py`:

```python
"""ProviderDataSource adapter tests (network paths mocked)."""
from unittest.mock import patch

from domain.models import KlineRow
from infrastructure.datasources.provider_datasource import ProviderDataSource


def test_get_klines_converts_rows_and_source():
    fake_rows = [
        {"time": "2026-08-22", "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 100},
    ]
    with patch("infrastructure.datasources.provider_datasource.providers.get_kline_with_source",
               return_value=(fake_rows, "live")):
        rows = ProviderDataSource().get_klines("us", "AAPL", "d", limit=30)
    assert rows == [
        KlineRow("2026-08-22", 1.0, 2.0, 0.5, 1.5, 100),
    ]


def test_reference_fx_rate_falls_back_to_static():
    with patch("infrastructure.datasources.provider_datasource.providers.get_live_fx_rates",
               return_value=None):
        rate = ProviderDataSource().reference_fx_rate("USD")
    assert rate == 7.18
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_provider_datasource.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现适配器**

`backend/infrastructure/datasources/__init__.py`：空文件。

`backend/infrastructure/datasources/provider_datasource.py`:

```python
"""Adapter wrapping the existing core.providers network layer."""
from __future__ import annotations

from core import providers
from domain.models import Instrument, KlineRow
from domain.valuation.currency import STATIC_FX_RATES


def _to_kline_rows(rows: list[dict]) -> list[KlineRow]:
    return [
        KlineRow(
            time=row["time"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
        )
        for row in rows
    ]


class ProviderDataSource:
    def list_instruments(self, market: str, top_n: int) -> list[Instrument]:
        items = providers.list_candidates(market, top_n)
        return [
            Instrument(
                market=item.get("market", market),
                symbol=item["symbol"],
                name=item.get("name", item["symbol"]),
                currency=item.get("currency", "USD"),
                sector=item.get("sector"),
                base_risk=item.get("base_risk"),
                liquidity=item.get("liquidity"),
            )
            for item in items
        ]

    def get_klines(self, market: str, symbol: str, period: str,
                   start: str | None = None, end: str | None = None,
                   limit: int = 180) -> list[KlineRow]:
        rows, _ = self.get_klines_with_source(market, symbol, period, start, end, limit)
        return rows

    def get_klines_with_source(self, market: str, symbol: str, period: str,
                               start: str | None = None, end: str | None = None,
                               limit: int = 180) -> tuple[list[KlineRow], str]:
        rows, source = providers.get_kline_with_source(
            market, symbol, period, limit, prefer_real=True,
        )
        if start:
            rows = [row for row in rows if row["time"] >= start]
        if end:
            rows = [row for row in rows if row["time"] <= end]
        return _to_kline_rows(rows), source

    def get_live_fx_rates(self) -> dict[str, float] | None:
        return providers.get_live_fx_rates()

    def reference_fx_rate(self, currency: str) -> float:
        try:
            live = providers.get_live_fx_rates()
            if live and currency in live:
                return live[currency]
        except Exception:
            pass
        return STATIC_FX_RATES.get(currency, 1.0)
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_provider_datasource.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/infrastructure/datasources backend/tests/unit/test_provider_datasource.py
git commit -m "feat: 新增 ProviderDataSource 数据源适配器"
```

### Task 2.2: MacroNewsProvider 适配器

**Files:**
- Create: `backend/infrastructure/datasources/macro_provider.py`
- Test: `backend/tests/unit/test_macro_provider.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_macro_provider.py`:

```python
"""MacroNewsProvider adapter tests."""
from infrastructure.datasources.macro_provider import MacroNewsProvider


def test_market_bias_and_score():
    provider = MacroNewsProvider()
    assert isinstance(provider.market_bias("us"), (dict, type(None)))
    assert 0 <= provider.macro_score("us") <= 100


def test_news_items_filtered_by_market():
    provider = MacroNewsProvider()
    items = provider.news_items("us")
    assert isinstance(items, list)
    assert all({"利率", "美股", "美元"} & set(item["tags"]) for item in items)
```

- [ ] **Step 2: 确认测试失败**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_macro_provider.py -q`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现适配器**

`backend/infrastructure/datasources/macro_provider.py`:

```python
"""Macro/news adapter wrapping core.macro static data."""
from __future__ import annotations

from core import macro


_MARKET_TAGS = {
    "a-share": {"A股", "政策", "信用"},
    "fund": {"A股", "政策", "ETF"},
    "us": {"美股", "利率", "美元", "全球"},
    "kr": {"韩股", "半导体", "汇率", "全球"},
    "hk": {"港股", "南向资金", "政策"},
    "fx": {"汇率", "美元", "利率", "全球"},
    "crypto": {"数字货币", "ETF", "全球"},
}


class MacroNewsProvider:
    def market_bias(self, market: str) -> dict | None:
        return macro.MARKET_BIAS.get(market)

    def macro_score(self, market: str) -> float:
        return macro.macro_score_for(market)

    def news_items(self, market: str) -> list[dict]:
        wanted = _MARKET_TAGS.get(market, {"全球"})
        return [item for item in macro.NEWS_ITEMS if set(item["tags"]) & wanted]
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_macro_provider.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/infrastructure/datasources/macro_provider.py backend/tests/unit/test_macro_provider.py
git commit -m "feat: 新增宏观新闻数据端口实现"
```

---

## Phase 3: 应用服务

### Task 3.0: 符号解析服务

**Files:**
- Create: `backend/application/services/symbol_resolver.py`
- Test: `backend/tests/unit/test_symbol_resolver.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_symbol_resolver.py`:

```python
"""SymbolResolver tests using fake datasource."""
from unittest.mock import patch

from application.services.symbol_resolver import SymbolResolver


def test_detect_and_normalize_market():
    resolver = SymbolResolver(datasource=None)
    assert resolver.detect_market("AAPL") == "us"
    assert resolver.detect_market("688836") == "a-share"
    assert resolver.normalize_symbol("kr", "005930") == "005930.KS"


def test_resolve_meta_probes_datasource_when_not_curated():
    class FakeDatasource:
        def get_klines(self, market, symbol, period, start=None, end=None, limit=180):
            return [
                KlineRow(
                    time=f"2026-08-{i:02d}", open=1.0, high=1.0,
                    low=1.0, close=100.0 + i, volume=1000,
                )
                for i in range(1, 61)
            ]

    resolver = SymbolResolver(datasource=FakeDatasource())
    meta = resolver.resolve_meta("us", "ZZZZ")
    assert meta is not None
    assert meta["symbol"] == "ZZZZ"
    assert meta["auto"] is True
```

测试文件头部补上 `from domain.models import KlineRow`。

- [ ] **Step 2: 实现 SymbolResolver**

`backend/application/services/symbol_resolver.py`:

```python
"""Cross-market symbol resolution without direct network access."""
from __future__ import annotations

import re

from application.ports import MarketDataSource
from domain.models import KlineRow
from domain.universe_data import find_symbol


_A_SHARE_SH = ("5", "6", "9")
_CRYPTO_SUFFIXES = ("USDT", "USDC", "BUSD", "BTC", "ETH", "SOL", "BNB",
                    "XRP", "DOGE", "ADA", "AVAX", "LINK")
_FX_PAIRS = {
    "USDCNY", "USDCNH", "EURUSD", "GBPUSD", "USDJPY", "USDHKD", "USDSGD",
    "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY",
}


class SymbolResolver:
    def __init__(self, datasource: MarketDataSource):
        self._datasource = datasource

    def detect_market(self, query: str) -> str | None:
        q = (query or "").strip().upper()
        if not q:
            return None
        if q.endswith(".KS") or q.endswith(".KQ"):
            return "kr"
        if q.endswith(".HK"):
            return "hk"
        if q.endswith((".SS", ".SH", ".SZ")):
            return "a-share"
        if q.endswith("=X") or q in _FX_PAIRS:
            return "fx"
        if any(q.endswith(s) for s in _CRYPTO_SUFFIXES):
            return "crypto"
        if q.isdigit():
            if len(q) == 6:
                if q.startswith(_A_SHARE_SH):
                    return "fund" if q.startswith("5") else "a-share"
                return "fund" if q.startswith(("1", "5")) else "a-share"
            return None
        if q.isalpha():
            return "us"
        return None

    def normalize_symbol(self, market: str, symbol: str) -> str:
        sym = symbol.strip().upper()
        if market == "kr":
            return f"{sym.split('.')[0]}.KS"
        if market == "hk":
            return f"{sym.split('.')[0]}.HK"
        if market == "fx":
            return f"{sym.split('=')[0]}=X"
        if market == "crypto":
            code = sym.split("_")[0].split("-")[0].split("/")[0]
            return f"{code}USDT"
        return sym

    def currency_for(self, market: str) -> str:
        return {
            "a-share": "CNY", "fund": "CNY", "us": "USD", "kr": "KRW",
            "hk": "HKD", "fx": "MULTI", "crypto": "USDT",
        }.get(market, "USD")

    def resolve_meta(self, market: str, symbol: str) -> dict | None:
        curated = find_symbol(market, symbol)
        if curated is not None:
            return dict(curated)
        rows = self._datasource.get_klines(market, symbol, "d", limit=60)
        if not rows:
            return None
        closes = [row.close for row in rows]
        name = self._fallback_name(market, symbol)
        sector = self._fallback_sector(market, symbol)
        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "currency": self.currency_for(market),
            "sector": sector,
            "base_risk": self._derive_risk(len(closes)),
            "liquidity": self._derive_liquidity(rows),
            "auto": True,
            "_probe_price": closes[-1],
        }

    @staticmethod
    def _derive_risk(row_count: int) -> float:
        return 0.58 if row_count >= 21 else 0.65

    @staticmethod
    def _derive_liquidity(rows: list[KlineRow]) -> float:
        volumes = [row.volume for row in rows[-20:]]
        if not volumes:
            return 0.7
        mean_volume = sum(volumes) / len(volumes)
        for floor, score in [(5e7, 0.95), (1e7, 0.85), (3e6, 0.7), (8e5, 0.5)]:
            if mean_volume >= floor:
                return score
        return 0.35

    @staticmethod
    def _fallback_name(market: str, symbol: str) -> str:
        names = {
            "a-share": "A股", "fund": "基金", "us": "美股", "kr": "韩股",
            "hk": "港股", "fx": "外汇", "crypto": "数字货币",
        }
        return f"{symbol} ({names.get(market, '标的')})"

    @staticmethod
    def _fallback_sector(market: str, symbol: str) -> str:
        return {
            "fx": "汇率", "crypto": "加密资产", "fund": "基金",
            "kr": "韩股", "hk": "港股",
        }.get(market, "未分类")
```

- [ ] **Step 3: 修正并运行测试**

将测试中的 fake datasource 返回列表改为 `KlineRow(...)` 对象（保留 time/open/high/low/close/volume 字段），然后：

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_symbol_resolver.py -q`
Expected: PASS（2 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/application/services/symbol_resolver.py backend/tests/unit/test_symbol_resolver.py
git commit -m "feat: 新增跨市场符号解析应用服务"
```

### Task 3.1: AnalysisService

**Files:**
- Create: `backend/application/services/analysis_service.py`
- Test: `backend/tests/unit/test_analysis_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_analysis_service.py`:

```python
"""AnalysisService tests."""
from unittest.mock import MagicMock

from application.services.analysis_service import AnalysisService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_analyze_returns_compatible_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    sync = MagicMock()
    sync.sync.return_value = []
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
  service = AnalysisService(repo, sync, resolver, macro)
    result = service.analyze("us", "AAPL")
    assert result["meta"]["symbol"] == "AAPL"
    assert result["kline_count"] == 60
    assert "analysis" in result
```

- [ ] **Step 2: 实现 AnalysisService**

`backend/application/services/analysis_service.py`:

```python
"""Single-instrument analysis orchestration."""
from __future__ import annotations

from application.ports import MacroNewsProvider, MarketDataRepository
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.indicators import analyze


class AnalysisService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 macro_news: MacroNewsProvider):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._macro = macro_news

    def analyze(self, market: str, symbol: str) -> dict:
        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            self._sync.sync(market, symbol, "d")
            rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        enriched = dict(meta)
        enriched["macro_score"] = self._macro.macro_score(market)
        kline_dicts = [
            {
                "time": row.time, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close, "volume": row.volume,
            }
            for row in rows
        ]
        result = analyze(kline_dicts, enriched)
        return {
            "meta": meta,
            "macro_bias": self._macro.market_bias(market),
            "analysis": result,
            "kline_count": len(rows),
        }

    def kline(self, market: str, symbol: str, period: str,
              limit: int, prefer_real: bool = True) -> tuple[list[dict], str]:
        rows = self._repository.get_klines(market, symbol, period)
        if rows:
            return [row.__dict__ for row in rows[-limit:]], "local"
        _, source = self._sync.sync(market, symbol, period)
        rows = self._repository.get_klines(market, symbol, period)
        return [row.__dict__ for row in rows[-limit:]], source if rows else "mock"

    def recommend(self, market: str, symbol: str) -> dict:
        """Compatibility shape for the legacy /api/recommend endpoint."""
        from domain.algorithms.config import build_engine
        from domain.algorithms.context import AnalysisContext

        meta = self._resolver.resolve_meta(market, symbol)
        if meta is None:
            return {"error": "symbol not found"}
        rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            self._sync.sync(market, symbol, "d")
            rows = self._repository.get_klines(market, symbol, "d")
        if not rows:
            return {"error": "no kline data", "market": market, "symbol": symbol}
        currency = meta.get("currency") or self._resolver.currency_for(market)
        ctx = AnalysisContext(
            symbol=symbol,
            market=market,
            currency=currency,
            klines=[
                {
                    "time": row.time, "open": row.open, "high": row.high,
                    "low": row.low, "close": row.close, "volume": row.volume,
                }
                for row in rows
            ],
            macro_bias=self._macro.macro_score(market),
            news_sentiment=0.0,
            fx_rate=None,
            horizon="short",
        )
        engine = build_engine()
        factor_scores = {}
        factor_details = {}
        for factor in engine.factors:
            result = factor.score(ctx)
            factor_scores[factor.name] = result["score"]
            factor_details[factor.name] = result.get("detail", {})
        sentiment = engine.sentiment.analyze(ctx)
        combined = engine.combine(factor_scores, sentiment)
        return {
            "meta": meta,
            "market": market,
            "symbol": symbol,
            "currency": currency,
            "factor_scores": factor_scores,
            "factor_details": factor_details,
            "sentiment": sentiment,
            "total_score": combined["total_score"],
            "detail": combined.get("detail", {}),
        }
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_analysis_service.py -q`
Expected: PASS（1 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/application/services/analysis_service.py backend/tests/unit/test_analysis_service.py
git commit -m "feat: 新增单标的分析应用服务"
```

### Task 3.2: ComparisonService

**Files:**
- Create: `backend/application/services/comparison_service.py`
- Test: `backend/tests/unit/test_comparison_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_comparison_service.py`:

```python
"""ComparisonService tests."""
from unittest.mock import MagicMock

from application.services.comparison_service import ComparisonService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_compare_sorts_assets_by_calmar():
    repo = MagicMock()
    repo.get_klines.side_effect = lambda market, symbol, period, **kw: _rows()
    sync = MagicMock()
    resolver = MagicMock()
    resolver.detect_market.side_effect = lambda token: {
        "AAPL": "us", "600519": "a-share",
    }.get(token)
    resolver.normalize_symbol.side_effect = lambda market, token: token
    resolver.currency_for.side_effect = lambda market: "USD"
    fx = MagicMock()
    fx.reference_fx_rate.return_value = 7.18
    service = ComparisonService(repo, sync, resolver, fx)
    result = service.compare("AAPL,600519")
    assert result["total"] == 2
    assert all("calmar_ratio" in item for item in result["items"])
```

- [ ] **Step 2: 实现 ComparisonService**

`backend/application/services/comparison_service.py`:

```python
"""Cross-asset comparison orchestration with injected fx rates."""
from __future__ import annotations

from application.ports import FxRateProvider, MarketDataRepository
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.valuation import currency as currency_util
from domain.valuation.constraints import quota_note, requires_quota
from domain.valuation.metrics import (
    annualized_return, calmar_ratio, max_drawdown, sharpe_ratio,
)


class ComparisonService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 fx_provider: FxRateProvider):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._fx = fx_provider

    def compare(self, symbols: str) -> dict:
        tokens = [token.strip() for token in symbols.split(",") if token.strip()]
        assets = []
        for token in tokens:
            market = self._resolver.detect_market(token)
            if market is None:
                continue
            symbol = self._resolver.normalize_symbol(market, token)
            rows = self._repository.get_klines(market, symbol, "d")
            if not rows:
                self._sync.sync(market, symbol, "d")
                rows = self._repository.get_klines(market, symbol, "d")
            if not rows:
                continue
            currency = self._resolver.currency_for(market)
            fx_rate = self._fx.reference_fx_rate(currency)
            closes = [row.close for row in rows]
            assets.append({
                "symbol": symbol,
                "name": token,
                "market": market,
                "currency": currency,
                "rmb_closes": currency_util.to_rmb_closes(closes, fx_rate),
            })
        return {"items": self._compare_assets(assets), "total": len(assets)}

    def _compare_assets(self, assets: list[dict]) -> list[dict]:
        results = []
        for asset in assets:
            closes = asset["rmb_closes"]
            calmar = calmar_ratio(closes)
            quota = requires_quota(asset["market"])
            results.append({
                "symbol": asset["symbol"],
                "name": asset["name"],
                "market": asset["market"],
                "currency": asset["currency"],
                "rmb_annual_return": round(annualized_return(closes), 4),
                "max_drawdown": round(max_drawdown(closes), 4),
                "calmar_ratio": round(calmar, 4) if calmar is not None else None,
                "sharpe_ratio": round(sharpe_ratio(closes), 4),
                "requires_quota": quota,
                "quota_note": quota_note(0.0) if quota else "",
            })
        results.sort(key=lambda item: (item["calmar_ratio"] is None,
                                       -(item["calmar_ratio"] or 0)))
        return results
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_comparison_service.py -q`
Expected: PASS（1 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/application/services/comparison_service.py backend/tests/unit/test_comparison_service.py
git commit -m "feat: 新增跨资产比较应用服务"
```

### Task 3.3: ScreeningService

**Files:**
- Create: `backend/application/services/screening_helpers.py`
- Create: `backend/application/services/screening_service.py`
- Test: `backend/tests/unit/test_screening_service.py`

- [ ] **Step 1: 迁移推荐原因构建逻辑**

`backend/application/services/screening_helpers.py`（从 `core/screener.py` 迁移 `_asset_type`、`_market_name`、`REASON_LABELS`、`_reason_from_news`、`_build_reasons`；`_news_for_market` 改为调用 `MacroNewsProvider.news_items`）:

```python
"""Screening helpers: translating analysis results into user-facing reasons."""
from __future__ import annotations

from application.ports import MacroNewsProvider


REASON_LABELS = {
    "technical": "技术指标",
    "macro": "宏观分析",
    "geopolitics": "地缘政治",
    "fund_flow": "资金流向",
    "policy": "政策事件",
    "industry": "行业事件",
    "risk": "风险提示",
}


def asset_type(item: dict) -> str:
    market = item["market"]
    symbol = item["symbol"]
    if market == "fx":
        return "外汇对"
    if market == "crypto":
        return "数字货币对"
    if market == "fund":
        return "指数ETF" if symbol.startswith(("15", "51")) else "场外基金"
    if market == "us" and symbol == "SPY":
        return "股票ETF"
    return "股票"


def market_name(market_id: str) -> str:
    return {
        "a-share": "A股", "fund": "基金", "us": "美股", "kr": "韩股",
        "hk": "港股", "fx": "外汇", "crypto": "数字货币",
    }.get(market_id, market_id)


def _reason_from_news(news: dict, market_name: str) -> dict:
    tags = set(news["tags"])
    if tags & {"政策", "利率"}:
        reason_type = "policy"
        base_weight = 68
    elif tags & {"资金流", "南向资金", "ETF"}:
        reason_type = "fund_flow"
        base_weight = 66
    elif tags & {"半导体", "原油"}:
        reason_type = "industry"
        base_weight = 62
    else:
        reason_type = "geopolitics"
        base_weight = 55
    weight = round(base_weight + float(news.get("sentiment", 0)) * 40)
    weight = max(35, min(weight, 96))
    return {
        "type": reason_type,
        "label": REASON_LABELS[reason_type],
        "title": news["title"],
        "detail": f"事件来自{news['source']}，与{market_name}的{('、'.join(sorted(tags)[:2]))}主题相关。",
        "weight": weight,
    }


def build_reasons(item: dict, analysis: dict, macro_news: MacroNewsProvider) -> list[dict]:
    market_id = item["market"]
    market_name = market_name(market_id)
    reasons: list[dict] = []
    if analysis["trend_score"] >= 60:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "趋势结构占优",
            "detail": "短期与中期均线呈多头排列，价格运行于 20 日均线上方。",
            "weight": round(52 + analysis["trend_score"] * 0.35),
        })
    if analysis["macd_hist"] is not None and analysis["macd_hist"] > 0:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "MACD 动能转强",
            "detail": f"MACD 柱值为 {analysis['macd_hist']:.3f}，短周期动能位于零轴上方。",
            "weight": round(42 + analysis["momentum_score"] * 0.42),
        })
    rsi = analysis["rsi14"]
    if rsi is not None:
        if 45 <= rsi <= 65:
            reasons.append({
                "type": "technical", "label": REASON_LABELS["technical"],
                "title": "RSI 强势但不超买",
                "detail": f"RSI14 为 {rsi:.1f}，处于趋势偏强且未过热的位置。",
                "weight": 63,
            })
        elif rsi > 70:
            reasons.append({
                "type": "risk", "label": REASON_LABELS["risk"],
                "title": "短线动能偏热",
                "detail": f"RSI14 达到 {rsi:.1f}，若追高需要关注回撤风险。",
                "weight": 54,
            })
    if analysis["change_20d"] > 3:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "20 日动量为正",
            "detail": f"近 20 个交易日上涨 {analysis['change_20d']:.1f}%。",
            "weight": round(45 + min(analysis["change_20d"] * 1.1, 28)),
        })
    bias = macro_news.market_bias(market_id)
    if bias:
        reasons.append({
            "type": "macro", "label": REASON_LABELS["macro"],
            "title": f"{market_name}宏观因子占优",
            "detail": bias["label"],
            "weight": round(float(bias["score"]) * 0.92),
        })
    used_titles = {reason["title"] for reason in reasons}
    for news in macro_news.news_items(market_id):
        reason = _reason_from_news(news, market_name)
        if reason["title"] in used_titles:
            continue
        used_titles.add(reason["title"])
        reasons.append(reason)
        if len([r for r in reasons if r["type"] in REASON_LABELS]) >= 7:
            break
    if not reasons:
        reasons.append({
            "type": "technical", "label": REASON_LABELS["technical"],
            "title": "波动水平适配",
            "detail": "当前波动率与标的类型匹配，适合纳入观察组合。",
            "weight": 42,
        })
    reasons.sort(key=lambda reason: reason["weight"], reverse=True)
    return reasons[:7]
```

说明：`build_reasons` 的循环与旧版 `_build_reasons` 行为等价（最多 7 条）。

- [ ] **Step 2: 写 ScreeningService 测试**

`backend/tests/unit/test_screening_service.py`:

```python
"""ScreeningService tests with fake dependencies."""
from unittest.mock import MagicMock

from application.services.screening_service import ScreeningService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_screen_returns_expected_shape():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    sync = MagicMock()
    resolver = MagicMock()
    resolver.resolve_meta.return_value = {
        "symbol": "AAPL", "name": "Apple", "market": "us",
        "currency": "USD", "sector": "tech", "base_risk": 0.3,
        "liquidity": 0.9,
    }
    macro = MagicMock()
    macro.macro_score.return_value = 55.0
    macro.market_bias.return_value = {"label": "偏多", "score": 60}
    macro.news_items.return_value = []
    service = ScreeningService(
        repo, sync, resolver, macro, MagicMock(), candidates=[
            {"market": "us", "symbol": "AAPL", "name": "Apple",
             "currency": "USD", "sector": "tech", "base_risk": 0.3,
             "liquidity": 0.9},
        ],
    )
    result = service.screen(market="us")
    assert result["total_universe"] == 1
    assert result["items"][0]["symbol"] == "AAPL"
```

- [ ] **Step 3: 实现 ScreeningService**

`backend/application/services/screening_service.py`:

```python
"""Screening orchestration: candidates -> concurrent scoring -> filters."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from application.ports import MacroNewsProvider, MarketDataSource, MarketDataRepository
from application.services.screening_helpers import asset_type, build_reasons, market_name
from application.services.sync_service import SyncService
from application.services.symbol_resolver import SymbolResolver
from domain.indicators import analyze
from domain.universe_data import MARKETS, universe_for


class ScreeningService:
    def __init__(self, repository: MarketDataRepository,
                 sync_service: SyncService,
                 symbol_resolver: SymbolResolver,
                 macro_news: MacroNewsProvider,
                 datasource: MarketDataSource,
                 candidates: list[dict] | None = None):
        self._repository = repository
        self._sync = sync_service
        self._resolver = symbol_resolver
        self._macro = macro_news
        self._datasource = datasource
        self._candidates = candidates

    def _candidate_pool(self, market: str, candidates_per_market: int) -> list[dict]:
        if self._candidates is not None:
            return self._candidates
        if candidates_per_market > 0:
            if market == "all":
                return [
                    item
                    for market_info in MARKETS
                    for item in self._list_candidates(market_info["id"], candidates_per_market)
                ]
            return self._list_candidates(market, candidates_per_market)
        return universe_for(market)

    def _list_candidates(self, market: str, top_n: int) -> list[dict]:
        instruments = self._datasource.list_instruments(market, top_n)
        return [item.__dict__ for item in instruments]

    def _build_candidate(self, item: dict, min_score: float, max_risk: float,
                         min_trend: float, min_momentum: float,
                         min_rsi: float, max_rsi: float) -> dict | None:
        rows = self._repository.get_klines(item["market"], item["symbol"], "d")
        if not rows:
            self._sync.sync(item["market"], item["symbol"], "d")
            rows = self._repository.get_klines(item["market"], item["symbol"], "d")
        if not rows:
            return None
        kline_dicts = [
            {
                "time": row.time, "open": row.open, "high": row.high,
                "low": row.low, "close": row.close, "volume": row.volume,
            }
            for row in rows
        ]
        enriched = dict(item)
        enriched["macro_score"] = self._macro.macro_score(item["market"])
        analysis = analyze(kline_dicts, enriched)
        if "error" in analysis:
            return None
        rsi = analysis["rsi14"] or 50
        risk = (1 - item["base_risk"]) * 100
        if (analysis["total_score"] < min_score or risk > max_risk
                or analysis["trend_score"] < min_trend
                or analysis["momentum_score"] < min_momentum
                or rsi < min_rsi or rsi > max_rsi):
            return None
        return {
            "symbol": item["symbol"],
            "name": item["name"],
            "market": item["market"],
            "market_name": market_name(item["market"]),
            "asset_type": asset_type(item),
            "sector": item["sector"],
            "currency": item["currency"],
            "price": analysis["price"],
            "change_1d": analysis["change_1d"],
            "change_20d": analysis["change_20d"],
            "rsi14": analysis["rsi14"],
            "trend_score": analysis["trend_score"],
            "momentum_score": analysis["momentum_score"],
            "volatility20": analysis["volatility20"],
            "macro_score": analysis["macro_score"],
            "total_score": analysis["total_score"],
            "signals": analysis["signals"][:3],
            "reasons": build_reasons(item, analysis, self._macro),
        }

    def screen(self, market: str = "all", min_score: float = 0,
               max_risk: float = 100, min_trend: float = 0,
               min_momentum: float = 0, min_rsi: float = 0,
               max_rsi: float = 100, sort_by: str = "total_score",
               limit: int = 60, candidates_per_market: int = 0) -> dict:
        items = self._candidate_pool(market, candidates_per_market)

        def build(item):
            return self._build_candidate(
                item, min_score, max_risk, min_trend, min_momentum,
                min_rsi, max_rsi,
            )

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = [r for r in executor.map(build, items) if r is not None]
        allowed_sort = {
            "total_score": "total_score",
            "change_20d": "change_20d",
            "rsi14": "rsi14",
            "trend_score": "trend_score",
        }
        key = allowed_sort.get(sort_by, "total_score")
        results.sort(key=lambda item: item[key], reverse=True)
        return {
            "items": results[:limit],
            "count": len(results),
            "total_universe": len(items),
        }
```

说明：`_list_candidates` 通过注入的 `MarketDataSource` 动态获取候选池；测试传入 `MagicMock()` 即覆盖固定候选池路径。

- [ ] **Step 4: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_screening_service.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/application/services/screening_helpers.py backend/application/services/screening_service.py backend/tests/unit/test_screening_service.py
git commit -m "feat: 新增筛选应用服务并迁移推荐原因构建"
```

### Task 3.4: RecommendationService

**Files:**
- Create: `backend/application/services/recommendation_service.py`
- Test: `backend/tests/unit/test_recommendation_service.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/test_recommendation_service.py`:

```python
"""RecommendationService tests."""
from unittest.mock import MagicMock

from application.services.recommendation_service import RecommendationService
from domain.models import KlineRow


def _rows():
    return [
        KlineRow(f"2026-08-{i:02d}", 1, 2, 0.5, 100.0 + i, 1000)
        for i in range(1, 61)
    ]


def test_recommendation_uses_daily_evaluation_cache():
    repo = MagicMock()
    repo.get_evaluation.return_value = {
        "items": [{"symbol": "AAPL"}], "count": 1, "total_universe": 1,
    }
    service = RecommendationService(repo, MagicMock())
    result = service.recommend()
    assert result["items"][0]["symbol"] == "AAPL"
```

- [ ] **Step 2: 实现 RecommendationService**

`backend/application/services/recommendation_service.py`:

```python
"""Cross-market recommendation orchestration with daily evaluation cache."""
from __future__ import annotations

from datetime import date

from application.ports import MarketDataRepository
from application.services.screening_service import ScreeningService


QUOTAS = {
    "a-share": 2, "us": 2, "kr": 1, "hk": 1, "fund": 1,
    "fx": 1, "crypto": 2,
}


class RecommendationService:
    def __init__(self, repository: MarketDataRepository,
                 screening_service: ScreeningService):
        self._repository = repository
        self._screening = screening_service

    def recommend(self, limit: int = 10, candidates_per_market: int = 0) -> dict:
        today = date.today().isoformat()
        cache_key = f"recommend:{limit}:{candidates_per_market}"
        cached = self._repository.get_evaluation(today, "all", cache_key)
        if cached is not None:
            return cached
        results = self._screening.screen(
            market="all",
            candidates_per_market=candidates_per_market,
            limit=100,
        )
        picked = self._pick(results["items"], limit)
        payload = {
            "items": picked,
            "count": len(picked),
            "total_universe": results["total_universe"],
        }
        self._repository.save_evaluation(
            today, "all", cache_key,
            len(picked), payload,
        )
        return payload

    def _pick(self, results: list[dict], limit: int) -> list[dict]:
        picked: list[dict] = []
        picked_keys: set[tuple[str, str]] = set()
        for market_id, quota in QUOTAS.items():
            group = [item for item in results if item["market"] == market_id]
            group.sort(key=lambda item: item["total_score"], reverse=True)
            for item in group[:quota]:
                picked.append(item)
                picked_keys.add((item["market"], item["symbol"]))
        remaining = [item for item in results
                     if (item["market"], item["symbol"]) not in picked_keys]
        remaining.sort(key=lambda item: item["total_score"], reverse=True)
        for item in remaining:
            if len(picked) >= limit:
                break
            picked.append(item)
            picked_keys.add((item["market"], item["symbol"]))
        market_presence = {item["market"] for item in picked}
        for required in ("fx", "crypto"):
            if required in market_presence:
                continue
            fallback = next((item for item in results if item["market"] == required), None)
            if fallback is not None:
                lowest = min(picked, key=lambda item: item["total_score"])
                picked.remove(lowest)
                picked.append(fallback)
                market_presence.add(required)
        picked.sort(key=lambda item: item["total_score"], reverse=True)
        return picked[:limit]
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_recommendation_service.py -q`
Expected: PASS（1 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/application/services/recommendation_service.py backend/tests/unit/test_recommendation_service.py
git commit -m "feat: 新增跨市场推荐应用服务并接入评估缓存"
```

---

## Phase 4: 展示层

### Task 4.1: 响应契约 schemas

**Files:**
- Create: `backend/presentation/__init__.py`
- Create: `backend/presentation/api/__init__.py`
- Create: `backend/presentation/api/schemas.py`
- Test: `backend/tests/unit/test_schemas.py`

- [ ] **Step 1: 写测试**

`backend/tests/unit/test_schemas.py`:

```python
"""Presentation schema tests."""
from presentation.api.schemas import ScreenQuery, symbols_list


def test_screen_query_defaults():
    q = ScreenQuery()
    assert q.market == "all"
    assert q.min_score == 0


def test_symbols_list_parser():
    assert symbols_list("AAPL,600519,,BTCUSDT") == ["AAPL", "600519", "BTCUSDT"]
```

- [ ] **Step 2: 实现 schemas**

`backend/presentation/api/schemas.py`:

```python
"""Request/response contracts. Response shapes stay compatible with the old API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenQuery(BaseModel):
    market: str = "all"
    min_score: float = Field(0, ge=0, le=100)
    max_risk: float = Field(100, ge=0, le=100)
    min_trend: float = Field(0, ge=0, le=100)
    min_momentum: float = Field(0, ge=0, le=100)
    min_rsi: float = Field(0, ge=0, le=100)
    max_rsi: float = Field(100, ge=0, le=100)
    sort_by: str = "total_score"
    limit: int = Field(60, ge=1, le=100)


def symbols_list(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_schemas.py -q`
Expected: PASS（2 passed）

- [ ] **Step 4: 提交**

```bash
git add backend/presentation backend/tests/unit/test_schemas.py
git commit -m "feat: 新增展示层请求响应契约"
```

### Task 4.2: 路由与依赖注入

**Files:**
- Create: `backend/presentation/api/routes.py`
- Create: `backend/presentation/dependencies.py`

- [ ] **Step 1: 实现 dependencies**

`backend/presentation/dependencies.py`:

```python
"""Dependency injection from the service container."""
from __future__ import annotations

from presentation.api import routes


def get_repository():
    return routes.container.repository


def get_datasource():
    return routes.container.datasource


def get_sync_service():
    return routes.container.sync_service


def get_analysis_service():
    return routes.container.analysis_service


def get_screening_service():
    return routes.container.screening_service


def get_recommendation_service():
    return routes.container.recommendation_service


def get_comparison_service():
    return routes.container.comparison_service
```

- [ ] **Step 2: 实现 routes**

`backend/presentation/api/routes.py`（保持原 API 路径与响应结构；`container` 在 `app.py` 中赋值）:

```python
"""HTTP routes: validation + service call + compatible response only."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from domain.universe_data import MARKETS, UNIVERSE, universe_for
from presentation.api.schemas import ScreenQuery


router = APIRouter()
container = None


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/api/markets")
def markets() -> dict:
    return {"items": MARKETS, "total": len(MARKETS)}


@router.get("/api/universe")
def universe(market: str = Query("all")) -> dict:
    items = universe_for(market)
    return {"items": items, "total": len(items)}


@router.get("/api/kline")
def kline(market: str, symbol: str, period: str = Query("d", pattern="^(h|d|w)$"),
          limit: int = Query(180, ge=30, le=1000), real: bool = Query(True)) -> dict:
    rows, source = container.analysis_service.kline(market, symbol, period, limit)
    return {
        "market": market, "symbol": symbol, "period": period,
        "count": len(rows), "source": source,
        "items": rows,
    }


@router.get("/api/analyze")
def analysis(market: str, symbol: str) -> dict:
    return container.analysis_service.analyze(market, symbol)


@router.get("/api/screen")
def run_screen(q: ScreenQuery = Depends()) -> dict:
    result = container.screening_service.screen(
        market=q.market, min_score=q.min_score, max_risk=q.max_risk,
        min_trend=q.min_trend, min_momentum=q.min_momentum,
        min_rsi=q.min_rsi, max_rsi=q.max_rsi, sort_by=q.sort_by, limit=q.limit,
    )
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@router.get("/api/recommendations")
def recommendations(limit: int = Query(10, ge=1, le=20),
                    candidates_per_market: int = Query(20, ge=0, le=100)) -> dict:
    result = container.recommendation_service.recommend(limit, candidates_per_market)
    result["updated_at"] = datetime.now(timezone.utc).isoformat()
    return result


@router.get("/api/macro")
def macro_payload(live_news: bool = Query(False)) -> dict:
    return container.macro_payload(live_news)


@router.get("/api/search")
def search_instruments_endpoint(q: str = Query("", max_length=64)) -> dict:
    return container.search(q)


@router.get("/api/recommend")
def recommend_symbol(market: str, symbol: str) -> dict:
    return container.analysis_service.recommend(market, symbol)


@router.get("/api/compare")
def compare_symbols(symbols: str = Query("")) -> dict:
    return container.comparison_service.compare(symbols)
```

说明：`container.search` 是 `ServiceContainer` 上为兼容旧 `/api/search` 端点保留的轻量适配方法，具体见 Task 4.3。

- [ ] **Step 3: 提交**

```bash
git add backend/presentation
git commit -m "feat: 新增展示层路由与依赖注入"
```

### Task 4.3: app.py composition root

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/contracts/test_api_contracts.py`

- [ ] **Step 1: 重写 app.py**

`backend/app.py`：

```python
"""FastAPI composition root: build services, register routes."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.config import AppConfig
from application.ports import MarketDataSource
from application.services.analysis_service import AnalysisService
from application.services.catalog_service import CatalogService
from application.services.comparison_service import ComparisonService
from application.services.recommendation_service import RecommendationService
from application.services.screening_service import ScreeningService
from application.services.symbol_resolver import SymbolResolver
from application.services.sync_service import SyncService
from domain.universe_data import UNIVERSE
from infrastructure.datasources.macro_provider import MacroNewsProvider
from infrastructure.datasources.provider_datasource import ProviderDataSource
from infrastructure.repository.sqlite import SqliteMarketDataRepository
from presentation.api.routes import router


@dataclass
class ServiceContainer:
    config: AppConfig
    repository: SqliteMarketDataRepository
    datasource: MarketDataSource
    macro_news: MacroNewsProvider
    symbol_resolver: SymbolResolver
    catalog_service: CatalogService
    sync_service: SyncService
    screening_service: ScreeningService
    recommendation_service: RecommendationService
    comparison_service: ComparisonService
    analysis_service: AnalysisService

    def search(self, query: str) -> dict:
        from core.search import search
        return search(query)

    def macro_payload(self, live_news: bool = False) -> dict:
        from core import macro
        payload = macro.macro_payload(live_news=live_news)
        payload["universe_size"] = len(UNIVERSE)
        return payload


def build_container(config: AppConfig | None = None,
                    datasource: MarketDataSource | None = None) -> ServiceContainer:
    config = config or AppConfig()
    repository = SqliteMarketDataRepository(config.db_path)
    datasource = datasource or ProviderDataSource()
    macro_news = MacroNewsProvider()
    symbol_resolver = SymbolResolver(datasource)
    catalog = CatalogService()
    sync_service = SyncService(repository, datasource)
    screening = ScreeningService(repository, sync_service, macro_news, datasource)
    recommendation = RecommendationService(repository, screening)
    comparison = ComparisonService(repository, sync_service, symbol_resolver, datasource)
    analysis = AnalysisService(
        repository, sync_service, symbol_resolver, macro_news, datasource,
    )
    return ServiceContainer(
        config=config, repository=repository, datasource=datasource,
        macro_news=macro_news, symbol_resolver=symbol_resolver,
        catalog_service=catalog, sync_service=sync_service, screening_service=screening,
        recommendation_service=recommendation,
        comparison_service=comparison, analysis_service=analysis,
    )


app = FastAPI(
    title="Global Finance Research Terminal",
    description="全球投资标的筛选与 K 线研究 API",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from presentation.api import routes as routes_module
routes_module.container = build_container()
app.include_router(router)
```

说明：`/api/kline` 通过 `AnalysisService.kline` 返回 `local` / `mock` / `live` 标识，`source` 由 `ProviderDataSource.get_klines_with_source` 透传到 `SyncService`。

- [ ] **Step 2: 写契约测试**

`backend/tests/contracts/test_api_contracts.py`:

```python
"""API response contract tests via TestClient."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from application.config import AppConfig
from app import app, build_container
from domain.models import KlineRow
from presentation.api import routes


@pytest.fixture(scope="module", autouse=True)
def wired_container():
    datasource = MagicMock()
    rows = [
        KlineRow(
            time=f"2026-08-{i:02d}", open=1.0, high=2.0,
            low=0.5, close=100.0 + i, volume=1000,
        )
        for i in range(1, 61)
    ]
    datasource.get_klines.return_value = rows
    datasource.get_klines_with_source.return_value = (rows, "live")
    datasource.list_instruments.return_value = []
    datasource.reference_fx_rate.return_value = 7.18
    datasource.get_live_fx_rates.return_value = None
    routes.container = build_container(
        AppConfig(db_path=Path(tempfile.mkdtemp()) / "test.db"),
        datasource=datasource,
    )
    yield routes.container


def test_health_and_markets():
    client = TestClient(app)
    assert client.get("/api/health").json()["status"] == "ok"
    payload = client.get("/api/markets").json()
    assert payload["total"] > 0


def test_kline_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/kline?market=us&symbol=AAPL&limit=30").json()
    assert "source" in payload
    assert "items" in payload
    assert "count" in payload


def test_screen_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/screen?market=us&limit=5").json()
    assert set(payload) >= {"items", "count", "total_universe", "updated_at"}


def test_recommendations_contract_shape():
    client = TestClient(app)
    payload = client.get("/api/recommendations?limit=5").json()
    assert set(payload) >= {"items", "count", "total_universe", "updated_at"}
```

说明：契约测试通过 `wired_container` fixture 注入临时数据库和确定性假数据源，不触发真实网络，也不污染默认数据库。

- [ ] **Step 3: 运行契约测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/contracts/test_api_contracts.py -q`
Expected: PASS（4 passed）

- [ ] **Step 4: 全量回归**

Run: `cd backend && .venv/bin/python -m pytest -q -q`
Expected: 全部 PASS；若旧 `test_api.py` 因响应字段变化失败，按“字段保持不变”原则修复路由，而不是改测试。

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/contracts
git commit -m "feat: app.py 收敛为装配根并接入展示层路由"
```

### Task 4.4: source 语义单元测试

**Files:**
- Modify: `backend/tests/unit/test_analysis_service.py`

- [ ] **Step 1: 写 source 语义测试**

在 `backend/tests/unit/test_analysis_service.py` 追加：

```python
def test_kline_source_local_when_repository_has_data():
    repo = MagicMock()
    repo.get_klines.return_value = _rows()
    service = AnalysisService(repo, MagicMock(), MagicMock(), MagicMock())
    items, source = service.kline("us", "AAPL", "d", 30)
    assert source == "local"
    assert len(items) == 30


def test_kline_source_from_sync_when_repository_empty():
    repo = MagicMock()
    repo.get_klines.side_effect = [[], _rows()]
    sync = MagicMock()
    sync.sync.return_value = (_rows(), "live")
    service = AnalysisService(repo, sync, MagicMock(), MagicMock())
    items, source = service.kline("us", "AAPL", "d", 30)
    assert source == "live"
    assert len(items) == 30
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/unit/test_analysis_service.py -q`
Expected: PASS（3 passed，含 Task 3.1 的 1 个）

- [ ] **Step 3: 全量回归**

Run: `cd backend && .venv/bin/python -m pytest -q -q`
Expected: 全部 PASS

- [ ] **Step 4: 提交**

```bash
git add backend/tests/unit/test_analysis_service.py
git commit -m "test: 固化 kline 数据源标识 local/live/mock 语义"
```

### Task 4.5: 集成装配冒烟测试

**Files:**
- Create: `backend/tests/integration/__init__.py`
- Create: `backend/tests/integration/test_service_container.py`

- [ ] **Step 1: 写测试**

`backend/tests/integration/test_service_container.py`:

```python
"""Service container wiring smoke test."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from application.config import AppConfig
from app import build_container


def test_container_wires_all_services():
    datasource = MagicMock()
    container = build_container(
        AppConfig(db_path=Path(tempfile.mkdtemp()) / "test.db"),
        datasource=datasource,
    )
    assert container.analysis_service is not None
    assert container.screening_service is not None
    assert container.recommendation_service is not None
    assert container.comparison_service is not None
    assert container.sync_service is not None
    assert container.macro_payload(False)["universe_size"] > 0
```

说明：导入 `app` 会执行 composition root 并创建默认开发库 `backend/data/research.db`，这是预期行为；测试自身使用临时库。

- [ ] **Step 2: 运行测试**

Run: `cd backend && .venv/bin/python -m pytest -q tests/integration/test_service_container.py -q`
Expected: PASS（1 passed）

- [ ] **Step 3: 提交**

```bash
git add backend/tests/integration
git commit -m "test: 新增服务容器集成装配冒烟测试"
```

---

## Phase 5: 兼容层清理与文档

### Task 5.1: 清理 core 兼容层

**Files:**
- Delete: `backend/core/` 中已无引用的模块
- Test: 全量回归

- [ ] **Step 1: 找出残留引用**

Run: `cd backend && rg -n "from core|import core" app.py presentation application infrastructure domain tests -g '*.py'`

- [ ] **Step 2: 逐个迁移残留引用**

对每个仍指向 `core` 的引用：

- `core.algorithms.*` → `domain.algorithms.*`
- `core.indicators` → `domain.indicators`
- `core.valuation.*` → `domain.valuation.*`
- `core.universe` → `domain.universe_data`
- `core.providers` → `infrastructure.datasources.provider_datasource` 内部实现（把网络逻辑迁入 infra，core 版本删除）
- `core.search` → `application.services.symbol_resolver` + 展示层路由中的搜索适配
- `core.macro` → `infrastructure.datasources.macro_provider`
- `core.screener`、`core.comparison` → 应用服务已替代

`backend/tests/` 下仍指向 `core` 的旧测试一并迁移：

- `test_context.py` → 改导入 `domain.algorithms.context`
- `test_factors.py` / `test_engine.py` / `test_sentiment.py` → 改导入 `domain.algorithms.*`
- `test_valuation.py` / `test_metrics.py` → 改导入 `domain.valuation.*`
- `test_search.py` / `test_api.py` / `test_recommendations.py` / `test_live_fx.py` → 若只覆盖旧 `core` 路径，改为新层等价测试；若已被 Phase 3/4 的新测试覆盖，直接删除文件

完成后：

Run: `cd backend && rg -n "from core|import core" app.py presentation application infrastructure domain tests -g '*.py'`
Expected: 无输出

- [ ] **Step 3: 删除 core 包**

```bash
rm -rf backend/core
```

- [ ] **Step 4: 全量回归**

Run: `cd backend && .venv/bin/python -m pytest -q -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add -A backend
git commit -m "refactor: 删除 core 兼容层，统一四层结构"
```

### Task 5.2: 更新 README 与架构文档

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: 更新 README**

在 `README.md` 的“架构”一节替换为四层描述，并注明目录结构：`presentation/`、`application/`、`domain/`、`infrastructure/`，兼容层已移除。

- [ ] **Step 2: 更新 ARCHITECTURE.md**

用四层依赖倒置图替换原架构图，数据流改为：前端 → 路由 → 应用服务 → 仓库/数据源 → 领域算法。

- [ ] **Step 3: 提交**

```bash
git add README.md docs/ARCHITECTURE.md
git commit -m "docs: 同步四层架构与数据流文档"
```

---

## 完成标准

- [ ] `cd backend && .venv/bin/python -m pytest -q -q` 全部 PASS。
- [ ] `backend/app.py` 不承载业务逻辑，只做装配与路由注册。
- [ ] `domain/` 不 import `infrastructure`、`providers`、`sqlite`、`fastapi`。
- [ ] 现有 `/api/*` 响应结构与迁移前一致（`source` 增加 `local` 取值不破坏前端）。
- [ ] 前端未改动，`frontend/src/types.ts` 无需更新即可工作。
