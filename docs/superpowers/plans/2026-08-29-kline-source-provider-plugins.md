# K 线数据源插件化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `warehouse/etl/sources/market.py` 拆分为每个数据源一个脚本，新增 `registry.py` 统一编排，ODS 改为贴源原样入仓，并新增 `sync_daily.py` 自动化入口。

**Architecture:** 源脚本统一 `fetch_klines(market, symbol, period, start, end, limit)` 返回 native 行；`registry.py` 按市场编排源链，真实源失败返回空，不写 mock；`sync_incremental.py` 使用 registry 并将 native 行原样写入 ODS；DWD 保持仓内标准化。

**Tech Stack:** Python 3.11、psycopg、pytest、PostgreSQL。

---

## 约定

- Python 解释器：`/Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python`
- 工作目录：`/Users/iRuiX/Documents/Project/finresearch/warehouse`
- 测试数据库 DSN：`postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse_test`
- 提交使用中文 message，类型用 `feat` / `fix` / `refactor` / `test` / `docs`。

---

### Task 1: 抽取公共基础设施

**Files:**
- Create: `warehouse/etl/sources/common.py`
- Test: `warehouse/tests/test_sources_common.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_common.py`:

```python
from datetime import date, timezone
from etl.sources import common


def test_parse_ts_handles_z_and_naive():
    assert common.parse_ts("2026-08-29T08:00:00Z").tzinfo is not None
    assert common.parse_ts("2026-08-29").date() == date(2026, 8, 29)


def test_aggregate_weekly_groups_iso_week():
    rows = [
        {"time": "2026-08-24T08:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
        {"time": "2026-08-25T08:00:00+00:00", "open": 1.5, "high": 3, "low": 1, "close": 2.5, "volume": 20},
    ]
    result = common.aggregate_weekly(rows)
    assert len(result) == 1
    assert result[0]["open"] == 1
    assert result[0]["close"] == 2.5
    assert result[0]["volume"] == 30
```

- [ ] **Step 2: 运行确认失败**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_common.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 common.py**

把 `market.py` 中的 `_get_json`、`_get_text`、`_parse_ts`、`_aggregate_weekly`、`_cache_get`、`_cache_set`、`_mark_dead`、`_is_dead`、`_try_provider` 移动到 `common.py`，去掉下划线前缀改为公共函数，并导出 `CACHE_TTL_SECONDS`。

`warehouse/etl/sources/common.py`:

```python
"""Shared HTTP, parsing, caching and circuit-breaking helpers."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen


CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, list[dict], str]] = {}
_cache_lock = threading.Lock()
_dead_providers: dict[str, float] = {}
_dead_lock = threading.Lock()


def get_json(url, timeout=8, headers=None):
    request_headers = {"User-Agent": "finresearch-warehouse/1.0"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_text(url, encoding="utf-8", timeout=8, headers=None):
    request_headers = {"User-Agent": "finresearch-warehouse/1.0"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode(encoding, errors="replace")


def parse_ts(value):
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def aggregate_weekly(rows):
    groups: dict[tuple[int, int], list[dict]] = {}
    for row in rows:
        try:
            day = parse_ts(row["time"]).date()
        except (TypeError, ValueError):
            continue
        groups.setdefault((day.isocalendar().year, day.isocalendar().week), []).append(row)
    weekly = []
    for _, group in groups.items():
        group.sort(key=lambda item: item["time"])
        weekly.append(
            {
                "time": group[-1]["time"],
                "open": group[0]["open"],
                "high": max(item["high"] for item in group),
                "low": min(item["low"] for item in group),
                "close": group[-1]["close"],
                "volume": sum(item["volume"] for item in group),
            }
        )
    weekly.sort(key=lambda item: item["time"])
    return weekly


def cache_get(key):
    with _cache_lock:
        hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, payload, source = hit
    if time.time() > expires_at:
        return None
    return payload, source


def cache_set(key, payload, source, ttl=CACHE_TTL_SECONDS):
    with _cache_lock:
        _cache[key] = (time.time() + ttl, payload, source)


def mark_dead(key):
    with _dead_lock:
        _dead_providers[key] = time.time() + 120


def is_dead(key):
    with _dead_lock:
        expires_at = _dead_providers.get(key)
    return expires_at is not None and time.time() < expires_at


def try_provider(name, key, function, *args):
    if is_dead(f"{name}:{key}"):
        return []
    try:
        rows = function(*args)
        if rows:
            return rows
    except Exception:
        mark_dead(f"{name}:{key}")
    return []
```

- [ ] **Step 4: 运行确认通过**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_common.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/sources/common.py warehouse/tests/test_sources_common.py
git commit -m "refactor: 抽取数据源公共基础设施"
```

---

### Task 2: 新增 tencent 数据源脚本

**Files:**
- Create: `warehouse/etl/sources/tencent.py`
- Test: `warehouse/tests/test_sources_tencent.py`

- [ ] **Step 1: 写失败测试**

`warehouse/tests/test_sources_tencent.py`:

```python
from etl.sources import tencent


def test_fetch_klines_parses_day_rows(monkeypatch):
    payload = {
        "data": {
            "sh600519": {
                "day": [["2026-08-01", "10", "10.5", "11", "9", "100"]],
            }
        }
    }
    monkeypatch.setattr(tencent, "get_json", lambda url, **kw: payload)
    rows = tencent.fetch_klines("a-share", "600519", "d", start="2026-08-01", end="2026-08-02")
    assert len(rows) == 1
    assert rows[0]["time"] == "2026-08-01"
    assert rows[0]["open"] == 10
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 100
```

- [ ] **Step 2: 运行确认失败**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_tencent.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: 实现 tencent.py**

`warehouse/etl/sources/tencent.py`:

```python
"""Tencent kline source."""
from __future__ import annotations

from urllib.parse import urlencode

from etl.sources.common import get_json, parse_ts


def _tencent_symbol(symbol: str, market: str) -> str:
    code = symbol.split(".")[0]
    if market == "a-share":
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return f"{prefix}{code}"
    if market == "fund":
        prefix = "sh" if code.startswith("5") else "sz"
        return f"{prefix}{code}"
    if market == "us":
        return f"us{code}.OQ"
    if market == "hk":
        return f"hk{code.zfill(5)}"
    raise ValueError(f"tencent does not support market {market}")


def _raw_klines(market: str, symbol: str, period: str, limit: int) -> list[dict]:
    t_symbol = _tencent_symbol(symbol, market)
    interval = {"h": "m60", "d": "day", "w": "week"}[period]
    adjust = "qfq" if market in ("a-share", "fund") else ""
    params = urlencode({"param": f"{t_symbol},{interval},,,{limit},{adjust}"})
    payload = get_json(
        f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?{params}",
        timeout=6,
        headers={"Referer": "https://gu.qq.com/"},
    )
    node = (payload or {}).get("data", {}).get(t_symbol, {})
    raw_rows = node.get(f"qfq{interval}") or node.get(interval) or []
    if not raw_rows:
        raise ValueError(f"tencent returned no rows for {t_symbol}")
    rows = []
    for item in raw_rows:
        if len(item) < 5:
            continue
        timestamp = str(item[0])
        if period == "h" and " " in timestamp:
            timestamp = timestamp.replace(" ", "T") + ":00"
        rows.append(
            {
                "time": timestamp,
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[3]),
                "low": float(item[4]),
                "volume": float(item[5]) if len(item) > 5 else 0.0,
            }
        )
    if period == "h" and len(rows) < 2:
        raise ValueError("tencent returned insufficient hourly rows")
    return rows[-limit:]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    rows = _raw_klines(market, symbol, period, limit)
    if start:
        rows = [r for r in rows if parse_ts(r["time"]) >= parse_ts(start)]
    if end:
        rows = [r for r in rows if parse_ts(r["time"]) <= parse_ts(end)]
    return rows
```

- [ ] **Step 4: 运行确认通过**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests/test_sources_tencent.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/sources/tencent.py warehouse/tests/test_sources_tencent.py
git commit -m "feat: 新增 tencent 独立数据源脚本"
```

---

### Task 3: 新增 naver、gate、binance 数据源脚本

按 Task 2 的模式，分别创建 `naver.py`、`gate.py`、`binance.py`，统一入口 `fetch_klines`，并从 `common` 导入 `get_json`、`get_text`、`parse_ts`、`aggregate_weekly`。

`naver.py` 从 `market.py` 的 `naver_klines` 原样迁移，包装后过滤窗口。

`gate.py` 从 `market.py` 的 `gate_klines` 原样迁移，并保留 `quote_volume`、`trades_count`、`funding_rate`（Gate 返回数组不足时字段为 0）。

`binance.py` 从 `market.py` 的 `binance_klines` 原样迁移，并保留 `quote_volume`、`trades_count`。

测试文件：`test_sources_naver.py`、`test_sources_gate.py`、`test_sources_binance.py`，分别 monkeypatch 各模块的 `get_json` / `get_text`。

- [ ] **Step 1: 创建并运行三个源测试到失败**
- [ ] **Step 2: 实现三个源脚本**
- [ ] **Step 3: 运行测试到通过**
- [ ] **Step 4: 分别提交**

```bash
git add warehouse/etl/sources/naver.py warehouse/tests/test_sources_naver.py
git commit -m "feat: 新增 naver 独立数据源脚本"

git add warehouse/etl/sources/gate.py warehouse/tests/test_sources_gate.py
git commit -m "feat: 新增 gate 独立数据源脚本"

git add warehouse/etl/sources/binance.py warehouse/tests/test_sources_binance.py
git commit -m "feat: 新增 binance 独立数据源脚本"
```

---

### Task 4: 新增 frankfurter、eastmoney 数据源脚本

按同样模式创建 `frankfurter.py`、`eastmoney.py`。

`frankfurter.py` 的 native 行保留 `base`、`quote`、`rate`、`open`、`high`、`low`、`close`、`volume`。

`eastmoney.py` 的 native 行保留 `nav`、`accum_nav`、`daily_growth_pct` 和标准 OHLCV。

测试：`test_sources_frankfurter.py`、`test_sources_eastmoney.py`。

- [ ] **Step 1: 创建并运行测试到失败**
- [ ] **Step 2: 实现两个源脚本**
- [ ] **Step 3: 运行测试到通过**
- [ ] **Step 4: 分别提交**

```bash
git add warehouse/etl/sources/frankfurter.py warehouse/tests/test_sources_frankfurter.py
git commit -m "feat: 新增 frankfurter 独立数据源脚本"

git add warehouse/etl/sources/eastmoney.py warehouse/tests/test_sources_eastmoney.py
git commit -m "feat: 新增 eastmoney 独立数据源脚本"
```

---

### Task 5: 新增 yfinance、akshare 数据源脚本

创建 `yfinance.py`、`akshare.py`。

`yfinance.py` 保留 `adj_close`、`dividends`、`stock_splits` 和标准 OHLCV。

`akshare.py` 按市场分别解析 A 股/基金，保留源字段。

测试：`test_sources_yfinance.py`、`test_sources_akshare.py`，用 monkeypatch 替换 yfinance Ticker 与 akshare 接口。

- [ ] **Step 1: 创建并运行测试到失败**
- [ ] **Step 2: 实现两个源脚本**
- [ ] **Step 3: 运行测试到通过**
- [ ] **Step 4: 分别提交**

```bash
git add warehouse/etl/sources/yfinance.py warehouse/tests/test_sources_yfinance.py
git commit -m "feat: 新增 yfinance 独立数据源脚本"

git add warehouse/etl/sources/akshare.py warehouse/tests/test_sources_akshare.py
git commit -m "feat: 新增 akshare 独立数据源脚本"
```

---

### Task 6: 新增 discovery 数据源脚本

**Files:**
- Create: `warehouse/etl/sources/discovery.py`
- Test: `warehouse/tests/test_sources_discovery.py`

- [ ] **Step 1: 写失败测试**

```python
from etl.sources import discovery


def test_discover_us_kr_fx_uses_static(monkeypatch):
    assert any(i["symbol"] == "AAPL" for i in discovery.discover_instruments("us"))
    assert any(i["symbol"] == "005930.KS" for i in discovery.discover_instruments("kr"))
    assert any(i["symbol"] == "USDCNY=X" for i in discovery.discover_instruments("fx"))


def test_discover_a_share_uses_akshare_spot(monkeypatch):
    frame = type("Frame", (), {})()
    frame.columns = ["代码", "名称", "成交额"]
    frame.rows = [["600519", "贵州茅台", 1e9]]

    class AK:
        def stock_zh_a_spot_em(self):
            return frame

    monkeypatch.setattr(discovery, "_ak", lambda: AK())
    items = discovery.discover_instruments("a-share")
    assert items[0]["symbol"] == "600519"
```

注意：akshare 返回的是 pandas DataFrame，测试中应按现有 `_top_frame_candidates` 的 pandas 语义构造真实 DataFrame，而不是示例中的 `type` 伪对象。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 discovery.py**

把 `market.py` 中的 `_top_frame_candidates`、`_a_share_candidates`、`_hk_candidates`、`_fund_candidates`、`_crypto_candidates`、`_discover_dynamic`、`discover_instruments` 原样迁移到 `discovery.py`，并删除下划线前缀。`discover_instruments` 保持原有缓存逻辑，依赖 `common.get_json`。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/sources/discovery.py warehouse/tests/test_sources_discovery.py
git commit -m "feat: 新增 discovery 独立发现脚本"
```

---

### Task 7: 新增 registry 编排脚本

**Files:**
- Create: `warehouse/etl/sources/registry.py`
- Test: `warehouse/tests/test_sources_registry.py`

- [ ] **Step 1: 写失败测试**

```python
from etl.sources import registry


def test_fetch_klines_uses_first_successful_source(monkeypatch):
    calls = []

    def a_share_ok(market, symbol, period, start=None, end=None, limit=1000):
        calls.append("a")
        return [{"time": "2026-08-29", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]

    def a_share_empty(market, symbol, period, start=None, end=None, limit=1000):
        calls.append("b")
        return []

    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("ok", a_share_ok), ("empty", a_share_empty)])
    rows = registry.fetch_klines("a-share", "600519", "d")
    assert len(rows) == 1
    assert calls == ["a"]


def test_disabled_source_is_skipped(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_SOURCE_DISABLED", "empty")
    monkeypatch.setitem(registry.SOURCE_CHAINS, "a-share", [("empty", lambda *a, **k: []), ("ok", lambda *a, **k: [])])
    names = [name for name, _ in registry.enabled_sources("a-share")]
    assert "empty" not in names
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 registry.py**

`registry.py`:

```python
"""Kline source registry and orchestration."""
from __future__ import annotations

import os
from typing import Any, Callable

from etl.sources import (
    akshare,
    binance,
    eastmoney,
    frankfurter,
    gate,
    naver,
    tencent,
    yfinance,
)
from etl.sources.common import cache_get, cache_set, try_provider


SourceFn = Callable[..., list[dict[str, Any]]]


def _fund_chain(symbol: str):
    is_open_fund = not symbol.startswith(("15", "51"))
    if is_open_fund:
        return [("eastmoney", eastmoney.fetch_klines), ("tencent", tencent.fetch_klines), ("akshare", akshare.fetch_klines)]
    return [("tencent", tencent.fetch_klines), ("eastmoney", eastmoney.fetch_klines), ("akshare", akshare.fetch_klines)]


SOURCE_CHAINS: dict[str, list[tuple[str, SourceFn]]] = {
    "a-share": [("tencent", tencent.fetch_klines), ("akshare", akshare.fetch_klines)],
    "fund": [],
    "us": [("tencent", tencent.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "kr": [("naver", naver.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "hk": [("tencent", tencent.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "fx": [("frankfurter", frankfurter.fetch_klines), ("yfinance", yfinance.fetch_klines)],
    "crypto": [("gate", gate.fetch_klines), ("binance", binance.fetch_klines), ("yfinance", yfinance.fetch_klines)],
}


def enabled_sources(market: str) -> list[tuple[str, SourceFn]]:
    disabled = {
        item.strip()
        for item in os.environ.get("WAREHOUSE_SOURCE_DISABLED", "").split(",")
        if item.strip()
    }
    chain = _fund_chain("") if market == "fund" else SOURCE_CHAINS.get(market, [])
    return [(name, fn) for name, fn in chain if name not in disabled]


def fetch_klines(market, symbol, period="d", start=None, end=None, limit=1000):
    key = f"{market}:{symbol}:{period}:{limit}"
    cached = cache_get(key)
    if cached is not None:
        rows, _ = cached
        if start:
            rows = [r for r in rows if r["time"] >= start]
        if end:
            rows = [r for r in rows if r["time"] <= end]
        return rows

    for name, fn in enabled_sources(market):
        rows = try_provider(name, key, fn, market, symbol, period, start, end, limit)
        if rows:
            cache_set(key, rows, "live")
            return rows
    return []


def discover_instruments(market: str) -> list[dict[str, Any]]:
    from etl.sources import discovery

    return discovery.discover_instruments(market)
```

注意：`fund` 源链需要 symbol，所以 `enabled_sources` 需要接收 symbol。实现时改为 `enabled_sources(market, symbol)`，`fetch_klines` 传入 symbol。测试同步调整。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/sources/registry.py warehouse/tests/test_sources_registry.py
git commit -m "feat: 新增数据源注册表与编排"
```

---

### Task 8: 更新 sync_incremental 使用 registry 并贴源写入 ODS

**Files:**
- Modify: `warehouse/etl/sync_incremental.py`
- Test: `warehouse/tests/test_sync_incremental.py`

- [ ] **Step 1: 更新失败测试**

把 `test_sync_incremental.py` 中所有 `monkeypatch.setattr(market, ...)` 改为 `monkeypatch.setattr(registry, "discover_instruments", ...)` 和 `monkeypatch.setattr(registry, "fetch_klines", ...)`。

新增一个断言验证 ODS `raw_payload` 包含 native 字段：

```python
def test_ods_writes_native_raw_payload(dsn, sync_cleanup, monkeypatch):
    # fake registry 返回带 extra 字段的 native 行
    ...
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 修改 sync_incremental.py**

把 `from etl.sources import market` 改为 `from etl.sources import registry`，并把两处 `market.` 改为 `registry.`。

把构建 `market_ods_rows` 的逻辑改为贴源原样：

```python
ods_row = {
    "provider": "market",
    "market": market_id,
    "symbol": symbol,
    "interval": "d",
    "ts": row["time"],
    "raw_payload": row,
    "sync_batch_id": batch_id,
}
ods_row.update({k: v for k, v in row.items() if k != "time"})
```

FX 特殊处理移出 `sync_incremental.py`，改由 `frankfurter.py` 的 native 字段提供；`build_dwd.py` 的 `_map_ohlc` 需要改为优先从 `raw_payload`/native 字段读取 FX 的 `base/quote/rate`。若第一版保持兼容，也可保留现有 FX 映射，但不丢弃 native 字段。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**

```bash
git add warehouse/etl/sync_incremental.py warehouse/tests/test_sync_incremental.py
git commit -m "refactor: sync_incremental 改用 registry 并贴源写入 ODS"
```

---

### Task 9: 新增 sync_daily 自动化入口

**Files:**
- Create: `warehouse/etl/sync_daily.py`
- Test: `warehouse/tests/test_sync_daily.py`

- [ ] **Step 1: 写失败测试**

验证 `sync_daily.main` 调用 `registry.discover_instruments` 且不生成 mock。

- [ ] **Step 2: 实现 sync_daily.py**

```python
"""Daily real-data warehouse sync entrypoint for cron or desktop automation."""
from __future__ import annotations

import os
import sys

from etl.sources import registry
from etl.universe import static_universe_for


def main() -> int:
    original_discover = registry.discover_instruments

    def static_or_dynamic(market: str):
        static = static_universe_for(market)
        if static:
            return static
        try:
            return original_discover(market)
        except Exception:
            return []

    registry.discover_instruments = static_or_dynamic
    try:
        from etl.sync_incremental import main as sync_main

        sync_main()
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 运行确认通过**

- [ ] **Step 4: 提交**

```bash
git add warehouse/etl/sync_daily.py warehouse/tests/test_sync_daily.py
git commit -m "feat: 新增每日真实数据同步自动化入口"
```

---

### Task 10: 删除 market.py 并收尾验证

**Files:**
- Delete: `warehouse/etl/sources/market.py`
- Delete: `warehouse/tests/test_sources_market.py`
- Modify: `warehouse/README.md`

- [ ] **Step 1: 删除旧文件**

```bash
git rm warehouse/etl/sources/market.py warehouse/tests/test_sources_market.py
```

- [ ] **Step 2: 更新 README**

README 的每日增量命令改为：

```bash
cd warehouse
python -m etl.sync_daily
```

并说明 `WAREHOUSE_SOURCE_DISABLED` 可禁用数据源，真实源失败不写 mock。

- [ ] **Step 3: 运行全量 warehouse 测试**

Run: `cd warehouse && /Users/iRuiX/Documents/Project/finresearch/backend/.venv/bin/python -m pytest tests -q`
Expected: 全部 PASS，`warehouse_test` 测试库已初始化。

- [ ] **Step 4: 提交**

```bash
git add -A warehouse/etl/sources warehouse/tests warehouse/README.md
git commit -m "refactor: 移除 market.py 并完成数据源插件化"
```

---

## 完成标准

- [ ] `market.py` 已删除，`sync_incremental.py` 只依赖 `registry`
- [ ] 每个 K 线数据源是独立脚本，统一 `fetch_klines` 接口
- [ ] ODS 贴源原样写入 native 字段与 `raw_payload`
- [ ] 真实源失败返回空，不写 mock
- [ ] `sync_daily.py` 可一行命令调用并返回退出码
- [ ] `warehouse/tests` 全部 PASS
- [ ] README 同步更新
