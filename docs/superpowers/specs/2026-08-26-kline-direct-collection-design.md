# 数仓直采 K 线设计（移除 research.db 中转）

> 日期：2026-08-26
> 状态：待评审
> 范围：warehouse 直接采集全市场 K 线，`research.db` 退役；行情采集代码归属数仓

## 1. 目标与范围

### 1.1 目标

- 数仓 ODS 全部直接从数据源获取：K 线由 `sync_incremental` 直采，不再经过 `research.db`。
- 全品类采集：A股 / 港股 / 场内基金 / 加密 / 外汇全市场动态发现、有数据就采；美股 / 韩股因无免费全量列表，走配置清单。
- 行情采集代码归属数仓（`warehouse/etl/sources/market.py`），backend 不再维护行情采集。

### 1.2 不做的事

- 不改动 backend 数据源层（`ProviderDataSource` 的候选/汇率能力保留，`symbol_resolver` 依赖保留）。
- 不恢复 backend 运行时同步。
- 不改变 `sync_external`（外部指标源）与 ODS/DWD/DWS 分层结构。
- 美股/韩股不做全市场（无免费公开全量列表），保持配置清单。

## 2. 架构

```text
外部行情源（腾讯 / Naver / Gate / Frankfurter / 东财 / yfinance / akshare / mock）
  ↓ warehouse/etl/sources/market.py（发现 + 采集 + 缓存熔断）
  ↓ sync_incremental 按水位线增量
ODS（ods_klines_* 直采）→ DWD（fact_kline）→ DWS（日频）
```

`research.db` 从 `sync_incremental` 链路移除；`migrate_seed.py` 降级为历史迁移工具。

## 3. 组件设计

### 3.1 `warehouse/etl/sources/market.py`

从 backend `provider_impl.py` 移植行情采集逻辑，仅保留数仓需要的能力：

- `discover_instruments(market) -> list[dict]`：按市场返回全量标的
  - A股：`stock_zh_a_spot_em` 全市场
  - 港股：`stock_hk_spot_em` 全市场
  - 场内基金：`fund_etf_spot_em` 全市场
  - 加密：Gate `/spot/tickers` 全部 USDT 交易对
  - 外汇：静态主要货币对清单（全部）
  - 美股 / 韩股：读 `warehouse/etl/universe.py` 配置清单
- `fetch_klines(market, symbol, period, start, end) -> list[dict]`：按市场路由主源/备用源，返回标准化 OHLCV 行
- 5 分钟缓存、120 秒失败熔断、确定性 mock 兜底（移植自 `provider_impl.py`）

### 3.2 `warehouse/etl/universe.py`

仅承载美股/韩股配置清单（复制 backend 内置代表标的）与外汇静态清单，其余市场由发现接口动态提供。

### 3.3 `sync_incremental` 改造

每日流程：

1. 对每个市场调用 `discover_instruments` 获取标的清单；
2. 逐个标的读取 `etl_watermarks`（scope `kline:{market}:{symbol}:{period}`）：
   - 有水位线：拉取 `(水位线, 今天]` 增量；
   - 无水位线（新标的）：拉取近 2 年历史（`2024-01-01` 至今）；
3. 映射为 ODS 行（provider 标记实际源），`upsert_ods_rows` 幂等写入；
4. 同事务内 `build_dwd`、推进水位线；
5. 事务提交后刷新 DWS。

请求节流：每标的请求间 `sleep`（默认 0.15s），失败沿用熔断机制跳过，不阻塞其他标的。

## 4. 数据流与水位线

- 新增标的首采：全量历史（近 2 年日线）。
- 存量标的：每日增量（水位线次日 → 今天）。
- 水位线格式与现有 `etl_watermarks` 一致（ISO 时间字符串）。
- 数仓 `dim_instrument` 由采集结果自动补齐（`build_dwd` 现有逻辑）。

## 5. 错误处理

- 单标的失败：熔断跳过、记 warning，不影响其他标的与市场。
- 全市场发现失败：跳过该市场，保留既有数据。
- 请求节流防限流；主源失败回退备用源，全部失败回退 mock 并标记。
- 事务内失败：该标的 ODS/DWD/水位线整体回滚，下次重跑。

## 6. 测试策略（TDD）

- `discover_instruments`：各市场发现函数单测（mock 网络响应/akshare），美股/韩股返回配置清单。
- `fetch_klines`：解析与路由单测（真实响应 fixture），失败回退链测试。
- `sync_incremental`：直采模式测试（mock `discover`/`fetch`）——首次全量、增量、失败回滚、水位线推进；不再读 `research.db`。
- 全量回归：warehouse 72 + backend 160 测试保持通过。

## 7. research.db 退役

- `sync_incremental` 删除 SQLite 读取路径。
- `migrate_seed.py` 保留（历史迁移工具），不再作为每日入口。
- README / 架构文档更新：K 线由数仓直采，`research.db` 仅保留为历史数据参考。
