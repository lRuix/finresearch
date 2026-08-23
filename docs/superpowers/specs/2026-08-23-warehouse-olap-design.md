# 独立 OLAP 数据仓库设计方案（纯 PostgreSQL）

> 日期：2026-08-23
> 状态：待评审
> 目标：在现有仓库内新增独立 `warehouse/` 子项目，以纯 PostgreSQL 构建分层数仓，先夯实底层数据，暂不与业务应用耦合。

---

## 1. 目标与边界

### 1.1 目标

- 独立构建数据仓库，与 `backend/` 业务应用解耦。
- 以 OLAP 视角设计 ODS / DWD / DWS / ADS 分层。
- 第一版尽量拉取最多、最多样、最稳定的底层数据，字段以数据源实际能力为准。
- 使用纯 PostgreSQL，不引入 TimescaleDB、DuckDB、StarRocks 等额外组件。

### 1.2 边界

- `warehouse/` 独立演进，未来可拆成独立仓库。
- 业务应用暂不消费数仓，先完成数据采集、建模、装载与质量校验。
- 不为拿不到的字段创建实体列；未解析字段放入 `raw_payload` 或 `extra JSONB`。

## 2. 技术栈与部署

- PostgreSQL 16，Docker Compose 启动。
- Python 3.11 + `psycopg` 作为 ETL 运行环境。
- 自有 `requirements.txt`、`docker-compose.yml`、`README.md`。
- 第一版不使用消息队列和调度框架，用脚本 + 事务保证一致性。

```text
warehouse/
├── docker-compose.yml
├── requirements.txt
├── README.md
├── etl/
│   ├── providers.py        # 数据源采集与字段解析
│   ├── load_ods.py         # 贴源装载
│   ├── build_dwd.py        # DWD 标准化装载
│   └── build_dws.py        # DWS 聚合刷新
├── models/
│   ├── 01_dim.sql
│   ├── 02_ods.sql
│   ├── 03_dwd.sql
│   └── 04_dws.sql
└── data/
    └── landing/            # 原始响应暂存，可审计
```

## 3. 分层模型

```text
ODS 贴源层：按市场分表，保留数据源原始字段
  ↓ 清洗、统一时区、去重、标准化
DWD 明细层：统一事实表 + 维度表
  ↓ 聚合
DWS 汇总层：日频指标
  ↓ 视图
ADS 应用层：暂不物化，以视图暴露
```

## 4. 数据源能力矩阵

状态：`已验证` 表示本轮联网实测；`待验证` 表示来源明确但当前网络环境未实测；`需扩展` 表示当前采集代码尚未解析。

| 数据域 | 字段 | 来源 | 状态 |
|---|---|---|---|
| A 股 | open/close/high/low/volume | 腾讯 | 已验证 |
| A 股 | amount/change_pct/turnover_rate/amplitude | 东方财富 / akshare | 待验证 |
| 场内 ETF | open/close/high/low/volume | 腾讯 | 已验证 |
| 场内 ETF | amount/change_pct/turnover_rate/amplitude | 东方财富 / akshare | 待验证 |
| 场外基金 | nav/accum_nav/daily_growth_pct/申购赎回状态/分红 | 东方财富 | 已验证 |
| 美股 | OHLCV | 腾讯 | 已验证 |
| 美股 | adj_close/dividends/stock_splits | yfinance | 已验证 |
| 港股 | open/close/high/low/volume + 分红回购事件 | 腾讯 | 已验证 |
| 港股 | amount_hkd | 东方财富 | 待验证 |
| 韩股 | OHLCV | Naver | 已验证 |
| 外汇 | close_rate/prev_rate | Frankfurter | 已验证 |
| 外汇 | OHLCV | yfinance `XXX=X` | 已验证 |
| 加密 | OHLCV/quote_volume | Gate / Binance | 已验证 |
| 加密 | trades_count | Binance | 已验证 |
| 加密 | funding_rate | Binance premiumIndex / Gate contracts | 已验证 |
| 加密 | market_cap/circulating_supply/total_supply | CoinGecko | 已验证 |
| 新闻 | title/source/tags/sentiment/published_at | FT 中文 / BBC RSS | 已验证 |

## 5. ODS 每市场 Schema

公共字段：

```sql
provider       TEXT NOT NULL,
market         TEXT NOT NULL,
symbol         TEXT NOT NULL,
interval       TEXT NOT NULL,
ts             TEXT NOT NULL,
raw_payload    JSONB NOT NULL DEFAULT '{}',
ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
sync_batch_id  TEXT NOT NULL
```

各市场特有字段：

| 表 | 特有字段 |
|---|---|
| `ods_klines_a_share` | `open/high/low/close/volume`、`amount`、`change_pct`、`turnover_rate`、`amplitude` |
| `ods_klines_fund` | ETF 的 OHLCV、`nav`、`accum_nav`、`daily_growth_pct`、`purchase_status`、`redeem_status` |
| `ods_klines_us` | `open/high/low/close/volume`、`adj_close`、`dividends`、`stock_splits` |
| `ods_klines_kr` | `open/high/low/close/volume` |
| `ods_klines_hk` | `open/high/low/close/volume`、`corporate_events` |
| `ods_klines_fx` | `base_currency`、`quote_currency`、`close_rate`、`prev_rate`、`open_rate`、`high_rate`、`low_rate` |
| `ods_klines_crypto` | `open/high/low/close/volume`、`quote_volume`、`trades_count`、`funding_rate` |
| `ods_news` | `title`、`source`、`tags`、`sentiment`、`published_at` |

幂等键：K 线 ODS 使用 `(provider, market, symbol, interval, ts)`；新闻使用 `(source, published_at, title)`。写入采用 `INSERT ... ON CONFLICT DO UPDATE`，避免重复。

## 6. DWD 明细模型

维度表：

- `dim_date`：`date_key`、`date`、`year`、`month`、`day`、`is_trading_day`
- `dim_market`：`market_id`、`name`、`region`、`currency`
- `dim_instrument`：`instrument_id`、`market_id`、`symbol`、`name`、`sector`
- `dim_provider`：`provider_id`、`name`

事实表：

- `fact_kline`：`market_id`、`instrument_id`、`provider_id`、`date_key`、`period`、`time`、`open`、`high`、`low`、`close`、`volume`
- `fact_news`：`news_id`、`source`、`published_at`、`title`、`sentiment`、`tags JSONB`

`fact_kline` 按 `time` 做范围分区，复合索引 `(market_id, instrument_id, period, time)`。

## 7. DWS 汇总模型

物化视图，日频刷新：

- `dws_instrument_daily`：标的日频收益率、振幅、成交量、成交额、波动率。
- `dws_market_daily`：市场日频平均涨跌、成交额合计、标的数。
- `dws_news_sentiment_daily`：按日聚合新闻情绪均值、正向/负向条数。

## 8. 装载与增量

1. 初始装载：从现有 `backend/data/research.db` 抽取 K 线，按市场映射写入 ODS，再标准化写入 DWD。
2. 新闻初始装载：从现有 `macro_data.NEWS_ITEMS` 与 RSS 抽取写入 `ods_news`。
3. 增量装载：按 `sync_watermarks` 读取数据源增量，ODS 与 DWD 在同一事务内完成，失败不推进水位线。
4. DWS 刷新：每轮装载结束后执行物化视图刷新。

## 9. 待验证项

- 东方财富 A 股 / 港股历史接口本轮返回 `RemoteDisconnected`，`amount/change_pct/turnover_rate/amplitude` 与港股成交额需在无代理环境复测后再启用。
- akshare 本轮受代理影响失败，其 A 股 / ETF 列名待复测确认。

## 10. 不做的事

- 不接入业务 API，不修改 `backend/` 与 `frontend/`。
- 不引入 TimescaleDB、DuckDB、StarRocks 或消息队列。
- 不为暂无来源的字段创建实体列。
- 不做复杂权限、多租户和分布式调度。
