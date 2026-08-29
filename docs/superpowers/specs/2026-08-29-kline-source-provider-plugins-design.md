# K 线数据源插件化与贴源 ODS 设计

## 目标

把数仓 K 线采集重构为“每个数据源一个独立脚本，统一入口可插拔编排”，并明确 ODS 为贴源原样镜像、DWD 负责仓内标准化。

## 现状问题

- `warehouse/etl/sources/market.py` 同时承载发现、缓存、熔断、所有数据源拉取与解析、mock 兜底，源与源之间耦合，扩展一个源需要改同一个大文件。
- `sync_incremental.py` 在写入 ODS 前只提取 `open/high/low/close/volume`，源返回的特色字段被丢弃，ODS 各市场的独有列没有真正被填满。
- 模拟数据兜底进入生产数仓，与“只要真实数据”的目标冲突。

## 架构原则

1. 每个数据源一个脚本，源脚本之间不 import，不互相耦合。
2. 源只负责拉取并解析成 native 行，返回该源真实结构，不做跨市场标准化。
3. ODS 贴源原样入仓：能映射到 ODS 列的同名字段直接写入，完整 native 对象写入 `raw_payload`，不丢字段。
4. DWD 在仓内做标准化，负责把 native 字段映射成统一事实字段。
5. 统一入口通过注册表编排源，支持运行时禁用源，可被 cron 或外部自动化调用。
6. 不生成、不写入 mock 数据；真实源失败就返回空，不自动兜底。

## 文件结构

```text
warehouse/etl/sources/
├── __init__.py
├── common.py
├── tencent.py
├── naver.py
├── gate.py
├── binance.py
├── frankfurter.py
├── eastmoney.py
├── yfinance.py
├── akshare.py
├── discovery.py
└── registry.py
```

删除 `warehouse/etl/sources/market.py`。`sync_incremental.py` 改为依赖 `registry`。

## Provider 协议

每个源脚本只暴露一个统一入口：

```python
def fetch_klines(
    market: str,
    symbol: str,
    period: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]
```

native 行只有一个最小公共约定：必须包含可解析的 `time`（ISO 8601 文本），用于窗口过滤和增量水位线。其他字段由该源自行定义，保留源自身特色。

## 数据流

```text
cron / 自动化
    ↓
sync_daily.py
    ↓
sync_incremental.py
    ↓
registry.fetch_klines / registry.discover_instruments
    ↓
各源脚本 fetch_klines → native rows
    ↓
ODS 贴源写入（同名列 + raw_payload 完整 native）
    ↓
build_dwd 仓内标准化 → fact_kline
    ↓
refresh_dws → 物化聚合
```

## 注册表与编排

`registry.py` 维护市场到源链的有序映射，按顺序尝试，第一个返回非空行的源生效。

内置源链：

- `a-share`: tencent → akshare
- `fund`: 场内/场外按 symbol 类型优先 tencent/eastmoney → akshare
- `us`: tencent → yfinance
- `kr`: naver → yfinance
- `hk`: tencent → yfinance
- `fx`: frankfurter → yfinance
- `crypto`: gate → binance → yfinance

支持环境变量：

- `WAREHOUSE_SOURCE_DISABLED`：逗号分隔需要禁用的源名
- `WAREHOUSE_MARKETS`：限定本次同步的市场
- `WAREHOUSE_DSN`：PostgreSQL 连接串

真实源全部失败时返回空列表，不写 mock。

## 各数据源 native 字段

每个源返回的字段由其 API 决定。第一版按现有实现解析并保留有意义字段：

- `tencent`：`time/open/high/low/close/volume`，A 股/基金保留腾讯返回的 `amount/change_pct/turnover_rate/amplitude` 等
- `naver`：`time/open/high/low/close/volume`
- `gate`：`time/open/high/low/close/volume/quote_volume/trades_count/funding_rate`
- `binance`：`time/open/high/low/close/volume/quote_volume/trades_count`
- `frankfurter`：`time/base/quote/rate/open/high/low/close/volume`
- `eastmoney`：`time/nav/accum_nav/daily_growth_pct/open/high/low/close/volume`
- `yfinance`：`time/open/high/low/close/volume/adj_close/dividends/stock_splits`
- `akshare`：按市场返回 A 股/基金对应字段

## ODS 贴源写入策略

`sync_incremental.py` 在拿到 native row 后：

1. 写入公共键：`provider/market/symbol/interval/ts`
2. 将 native row 中与目标 ODS 表列同名的字段直接写入对应列
3. 将完整 native row 写入 `raw_payload`
4. 写入 `sync_batch_id`

FX 市场在贴源时保留 native 字段；货币对解析由源脚本 native 字段携带，不在这里强压成 OHLCV。

## DWD 标准化策略

`build_dwd.py` 继续负责仓内标准化，以 ODS 列和 `raw_payload` 为输入，按市场规则提取统一事实字段：

- 股票/加密/港股/韩股：提取 `open/high/low/close/volume`
- 基金：优先 `nav`，缺失时回退 `close`
- 外汇：从 `base/quote/rate` 或 ODS 的 `*_rate` 列计算 OHLC 与 volume=0

特色字段仍保留在 ODS 和 `raw_payload`，第一版不在 DWD 中额外展开。

## 自动化入口

新增 `warehouse/etl/sync_daily.py`：

- 默认同步全部市场
- 动态发现失败时使用内置静态标的清单
- 真实源失败返回空，不写 mock
- 输出各市场 ODS/DWD 行数统计
- 成功退出码 `0`，失败退出码非 `0`

`sync_incremental.py` 保持现有 CLI 与函数签名，只把数据源依赖从 `market` 改为 `registry`。

## 错误处理、缓存与熔断

- 单个标的或单个市场失败只跳过当前标的/市场，不中断整个任务。
- 缓存与熔断逻辑放在 `common.py`，按 `market:symbol:period:source` 做失败熔断。
- 缓存只缓存成功拉取结果，不缓存 mock。

## 测试策略

- 删除 `warehouse/tests/test_sources_market.py`。
- 新增 `test_sources_registry.py`：验证源链路由、禁用源、真实源失败返回空、窗口过滤。
- 新增按源独立测试：`test_sources_tencent.py`、`test_sources_naver.py`、`test_sources_gate.py`、`test_sources_frankfurter.py`、`test_sources_discovery.py` 等。
- 更新 `test_sync_incremental.py`：monkeypatch 目标从 `market` 改为 `registry`，并验证 ODS 原样写入 native 字段与 `raw_payload`。
- 测试用 monkeypatch 打桩 HTTP 响应，不生成模拟数据。

## 兼容与迁移

- `sync_incremental.py`、`sync_daily.py` 是外部自动化和 CLI 的稳定入口。
- 移除 `market.py` 后，旧测试和调用方同步更新。
- `warehouse/etl/universe.py` 保留静态标的清单，并补齐 A 股/基金/港股/加密的代表性标的。

## 不在本次范围

- 不引入消息队列或调度框架，仍以 CLI 脚本为自动化单位。
- 不重构 `sync_external.py` 与外部非 K 线数据源。
- 不在 DWD 中展开所有源特色字段。
