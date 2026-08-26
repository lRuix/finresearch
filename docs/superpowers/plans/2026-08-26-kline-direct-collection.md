# 数仓直采 K 线实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `sync_incremental` 改为直采全市场 K 线（A股/港股/基金/加密/外汇全量，美股/韩股走配置清单），`research.db` 退出同步链路，行情采集代码归属数仓。

**Architecture:** 新增 `warehouse/etl/sources/market.py`（发现 + 采集 + 缓存熔断，移植自 backend `provider_impl.py`）与 `warehouse/etl/universe.py`（美股/韩股/外汇静态清单）；`sync_incremental` 按 `etl_watermarks` 水位线直采增量 K 线 → ODS → DWD → DWS。

**Tech Stack:** Python 3.12、psycopg 3、akshare（A股/港股/基金发现）、标准库 urllib（行情请求）。

**Spec:** `docs/superpowers/specs/2026-08-26-kline-direct-collection-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `warehouse/etl/universe.py` | 美股/韩股配置清单 + 外汇静态清单 |
| `warehouse/etl/sources/market.py` | 全市场发现 + K 线采集 + 缓存熔断（移植自 `backend/infrastructure/datasources/provider_impl.py`） |
| `warehouse/etl/sync_incremental.py` | 直采改造：不再读 research.db |
| `warehouse/tests/test_sources_market.py` | 发现/采集/回退测试 |
| `warehouse/tests/test_universe.py` | 配置清单测试 |
| `warehouse/tests/test_sync_incremental.py` | 直采模式增量/回滚测试（改造） |
| `warehouse/README.md` / `docs/ARCHITECTURE.md` | 文档同步 |

---

### Task 1: universe.py 配置清单

**Files:**
- Create: `warehouse/etl/universe.py`
- Test: `warehouse/tests/test_universe.py`

- [ ] **Step 1: 写失败测试 `warehouse/tests/test_universe.py`**

```python
"""Static universe configuration tests."""
from __future__ import annotations

from etl.universe import CONFIG_MARKETS, static_universe


def test_static_universe_covers_us_and_kr():
    symbols = {item["symbol"] for item in static_universe()}
    assert {"AAPL", "NVDA", "MSFT", "TSLA"} <= symbols
    assert {"005930.KS", "000660.KS"} <= symbols


def test_static_universe_has_market_and_currency():
    for item in static_universe():
        assert item["market"] in CONFIG_MARKETS
        assert item["currency"]


def test_fx_universe_has_major_pairs():
    symbols = {item["symbol"] for item in static_universe() if item["market"] == "fx"}
    assert {"USDCNY=X", "EURUSD=X"} <= symbols
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_universe.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.universe'`

- [ ] **Step 3: 实现 `warehouse/etl/universe.py`**

复制 backend `domain/universe_data.py` 中美股/韩股/外汇的条目（symbol/name/market/currency/sector/base_risk/liquidity），并导出：

```python
CONFIG_MARKETS = ("us", "kr", "fx")

def static_universe() -> list[dict]:
    """美股/韩股配置清单 + 外汇静态清单（无免费全量源的市场走这里）。"""
    return [dict(item) for item in _STATIC_UNIVERSE]
```

`_STATIC_UNIVERSE` 至少包含：美股 AAPL/NVDA/MSFT/TSLA/SPY，韩股 005930.KS/000660.KS/035420.KS/373220.KS，外汇 USDCNY=X/EURUSD=X/USDJPY=X/GBPUSD=X。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_universe.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/universe.py warehouse/tests/test_universe.py
git commit -m "feat: 数仓静态标的清单（美股/韩股/外汇）"
```

---

### Task 2: market.py 全市场发现（TDD）

**Files:**
- Create: `warehouse/etl/sources/market.py`
- Test: `warehouse/tests/test_sources_market.py`

- [ ] **Step 1: 写失败测试**

```python
"""Market discovery and kline fetching tests (network mocked)."""
from __future__ import annotations

from etl.sources import market


def test_discover_us_and_kr_use_static_universe(monkeypatch):
    items = market.discover_instruments("us")
    assert any(item["symbol"] == "AAPL" for item in items)
    items_kr = market.discover_instruments("kr")
    assert any(item["symbol"] == "005930.KS" for item in items_kr)


def test_discover_crypto_parses_gate_tickers(monkeypatch):
    payload = [
        {"currency_pair": "BTC_USDT", "quote_volume": "1000"},
        {"currency_pair": "ETH_USDT", "quote_volume": "900"},
        {"currency_pair": "BTC_ETH", "quote_volume": "999"},
        {"currency_pair": "USDT_USDT", "quote_volume": "1"},
    ]
    monkeypatch.setattr(market, "_get_json", lambda url, **kw: payload)
    items = market.discover_instruments("crypto")
    symbols = {item["symbol"] for item in items}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


def test_discover_a_share_uses_akshare_spot(monkeypatch):
    class FakeFrame:
        def to_dict(self, orient):
            return [
                {"代码": "600519", "名称": "贵州茅台", "成交额": 1e9},
                {"代码": "000001", "名称": "平安银行", "成交额": 2e9},
            ]

    monkeypatch.setattr(
        market,
        "_ak",
        lambda: type("AK", (), {"stock_zh_a_spot_em": lambda: FakeFrame()}),
    )
    items = market.discover_instruments("a-share")
    assert {item["symbol"] for item in items} == {"600519", "000001"}
    assert all(item["market"] == "a-share" for item in items)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sources_market.py -q`
Expected: `ModuleNotFoundError: No module named 'etl.sources.market'`

- [ ] **Step 3: 实现 `market.py` 的发现部分**

移植自 `backend/infrastructure/datasources/provider_impl.py`：

- `_get_json` / `_get_text`（urllib + User-Agent）
- `_ak()`：惰性 import akshare
- `_top_frame_candidates` / `_a_share_candidates` / `_hk_candidates` / `_fund_candidates`：akshare 全市场快照取全部（top_n 改为不截断或很大值）
- `_crypto_candidates`：Gate tickers 全量 USDT 交易对（过滤稳定币）
- `_fx_candidates`：静态清单全部
- `discover_instruments(market)`：按市场分发；美股/韩股返回 `static_universe()` 对应市场；未知市场返回空列表

发现结果带短缓存（5 分钟），避免每日同步内重复请求。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sources_market.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/market.py warehouse/tests/test_sources_market.py
git commit -m "feat: 数仓全市场标的发现"
```

---

### Task 3: market.py K 线采集（TDD）

**Files:**
- Modify: `warehouse/etl/sources/market.py`
- Modify: `warehouse/tests/test_sources_market.py`

- [ ] **Step 1: 写失败测试（追加到 test_sources_market.py）**

```python
def test_fetch_klines_routes_a_share_and_normalizes(monkeypatch):
    payload = {
        "data": {
            "600519": [
                {"d": "2026-08-01", "o": "10", "h": "11", "l": "9", "c": "10.5", "v": "100"},
            ]
        }
    }
    monkeypatch.setattr(market, "_get_json", lambda url, **kw: payload)
    rows = market.fetch_klines("a-share", "600519", "d", start="2026-08-01", end="2026-08-02")
    assert len(rows) == 1
    assert rows[0]["open"] == 10
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 100


def test_fetch_klines_falls_back_to_mock(monkeypatch):
    def boom(_url, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(market, "_get_json", boom)
    monkeypatch.setattr(market, "_ak", lambda: (_ for _ in ()).throw(RuntimeError("no akshare")))
    rows = market.fetch_klines("a-share", "600519", "d", start="2026-08-01", end="2026-08-02")
    assert rows  # mock 兜底返回确定性数据
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sources_market.py::test_fetch_klines_routes_a_share_and_normalizes -q`
Expected: `AttributeError: module 'etl.sources.market' has no attribute 'fetch_klines'`

- [ ] **Step 3: 实现 `fetch_klines` 与路由**

移植 `provider_impl.py` 的：

- 腾讯日线解析（A股/美股/港股/ETF `_tencent_klines` 等）
- Naver 韩股、Gate 加密、Frankfurter 外汇、东财基金、yfinance/akshare 备用源
- `mock_klines` 确定性兜底
- `get_kline_with_source` 路由：主源 → 备用源 → mock；带 5 分钟缓存与 120 秒熔断
- 暴露 `fetch_klines(market, symbol, period, start=None, end=None) -> list[dict]`（内部按 start/end 过滤，返回标准 OHLCV dict）

（这些函数从 backend `provider_impl.py` 原样移植，删除候选/汇率等无关部分。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sources_market.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add warehouse/etl/sources/market.py warehouse/tests/test_sources_market.py
git commit -m "feat: 数仓 K 线直采（主源/备用/mock 路由）"
```

---

### Task 4: sync_incremental 直采改造（TDD）

**Files:**
- Modify: `warehouse/etl/sync_incremental.py`
- Modify: `warehouse/tests/test_sync_incremental.py`

- [ ] **Step 1: 更新失败测试**

改造 `tests/test_sync_incremental.py`：把 `_seed_sqlite_db` / `_insert_sqlite_row` 改为 monkeypatch `market.discover_instruments` 与 `market.fetch_klines`：

```python
def _fake_discover():
    return [
        {"market": "a-share", "symbol": "TEST-SYNC-600519", "name": "T", "currency": "CNY"},
    ]


def _fake_fetch(market_id, symbol, period, start=None, end=None):
    return [
        {"time": "2026-08-01", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0},
        {"time": "2026-08-02", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.6, "volume": 110.0},
    ]


def test_first_run_collects_new_symbols(dsn, sync_cleanup, monkeypatch):
    monkeypatch.setattr(market, "discover_instruments", lambda m: _fake_discover() if m == "a-share" else [])
    monkeypatch.setattr(market, "fetch_klines", _fake_fetch)
    stats = sync_incremental(dsn, batch_id=f"test-sync-{uuid.uuid4()}")
    assert stats["klines"]["a-share"]["ods"] == 2
```

保留原有断言（ODS 行数、fact_kline、水位线、失败回滚），数据源从 SQLite 改为直采 mock。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sync_incremental.py -q`
Expected: 失败（`sync_incremental` 仍读 SQLite，无 `db_path` 参数路径）

- [ ] **Step 3: 改造 `sync_incremental.py`**

```python
def sync_incremental(dsn: str, include_rss: bool = False, batch_id: str | None = None) -> dict:
    """直采全市场 K 线增量：discover -> fetch -> ODS -> DWD -> 水位线。"""
    batch_id = batch_id or _new_batch_id()
    markets = ("a-share", "fund", "us", "kr", "hk", "fx", "crypto")
    with connect(dsn) as conn:
        watermarks = _read_watermarks(conn)
        kline_wm = {k: v for k, v in watermarks.items() if isinstance(k, tuple)}
        for market_id in markets:
            instruments = market.discover_instruments(market_id)
            for item in instruments:
                symbol = item["symbol"]
                key = (market_id, symbol, "d")
                last = kline_wm.get(key)
                start = (last + timedelta(days=1)).date().isoformat() if last else "2024-01-01"
                end = date.today().isoformat()
                try:
                    rows = market.fetch_klines(market_id, symbol, "d", start=start, end=end)
                except Exception:
                    continue
                if not rows:
                    continue
                ods_rows = [
                    {
                        "provider": "market",
                        "market": market_id,
                        "symbol": symbol,
                        "interval": "d",
                        "ts": row["time"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "raw_payload": {},
                        "sync_batch_id": batch_id,
                    }
                    for row in rows
                ]
                upsert_ods_rows(dsn, market_id, ods_rows, conn=conn)
                build_dwd(dsn, market_id, conn=conn)
                _set_kline_watermark(conn, key, rows[-1]["time"])
        conn.commit()
    refresh_dws(dsn)
    return stats
```

要点：保留新闻装载（`_upsert_news`）与水位线读写；删除 SQLite 读取（`iter_sqlite_klines_after` / `_mapped_sqlite_row` 相关）；`db_path` 参数移除；请求节流 `sleep(0.15)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests/test_sync_incremental.py -q`
Expected: 全部通过（首次全量、二次增量、失败回滚、新闻）

- [ ] **Step 5: 全量回归**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m pytest tests -q`
Expected: 全部通过

- [ ] **Step 6: Commit**

```bash
git add warehouse/etl/sync_incremental.py warehouse/tests/test_sync_incremental.py
git commit -m "feat: sync_incremental 直采全市场 K 线，移除 research.db 依赖"
```

---

### Task 5: 文档与端到端验证

- [ ] **Step 1: 更新 `warehouse/README.md` 与 `docs/ARCHITECTURE.md`**

K 线由数仓直采（A股/港股/基金/加密/外汇全量，美股/韩股配置清单）；`research.db` 不再参与每日同步（仅历史参考）；`migrate_seed.py` 为历史迁移工具。

- [ ] **Step 2: 端到端验证**

Run: `cd /Users/hxjs1/Documents/project/finresearch/warehouse && .venv/bin/python -m etl.sync_incremental`（escalation，联网）
Expected: 各市场输出 ODS 行数；`fact_kline` 有数据且覆盖多个市场。

再跑一次验证增量：Expected: 第二次 ODS 行数显著减少（仅当天增量）。

- [ ] **Step 3: Commit**

```bash
git add warehouse/README.md docs/ARCHITECTURE.md
git commit -m "docs: 同步数仓直采 K 线说明"
```
