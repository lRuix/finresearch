# 数仓外部数据源接入设计（SEC · CoinGecko · World Bank · akshare）

> 日期：2026-08-25
> 状态：待评审
> 范围：warehouse 数仓新增四类外部数据源，构建"贴源 ODS → 通用指标 DWD → 日频 DWS"链路

## 1. 目标与范围

### 1.1 目标

在 `warehouse/` 数仓中新增四类经过实测验证的外部数据源，补足行情之外的基本面、宏观与资金面数据域：

- **SEC EDGAR**：美股公司元数据、ticker 映射与 XBRL 财务指标（官方、免 key）。
- **CoinGecko**：加密资产市值/价格/成交量快照（官方、免 key、限流宽松）。
- **World Bank**：全球宏观指标序列（官方、免 key）。
- **akshare（同花顺/东方财富）**：A股财务摘要与龙虎榜明细（免费，接口偶发变动）。

### 1.2 不做的事

- 不接入需要 API key 的源（FRED 当前网络不可达、Alpha Vantage/Finnhub 需 key，均不在本期）。
- 不接入 Stooq（CSV 端点有 JS 反爬，无法脚本化）。
- 不改动 `backend/` 业务层与 `frontend/`；数据只进数仓。
- 不为文本类字段（如龙虎榜"解读/上榜原因"）建模进入指标事实表。

## 2. 架构与数据流

```text
SEC EDGAR / CoinGecko / World Bank / akshare(同花顺·东财)
   ↓ etl/sources/*.py 解析为统一 dict
   ↓ etl/sync_external.py 按源独立事务装载 + 水位线推进
ODS（按源贴存）→ DWD（dim_indicator + fact_indicator）→ DWS（dws_indicator_daily）
```

### 2.1 新增文件

- `warehouse/etl/sources/__init__.py`
- `warehouse/etl/sources/sec_edgar.py`：SEC submissions/companyfacts 抓取与解析
- `warehouse/etl/sources/coingecko.py`：CoinGecko 市值/价格解析
- `warehouse/etl/sources/worldbank.py`：World Bank 指标解析
- `warehouse/etl/sources/akshare_cn.py`：akshare A股财务摘要/龙虎榜解析
- `warehouse/etl/sync_external.py`：外部数据增量同步入口（main）
- `warehouse/tests/test_sources_sec.py` / `test_sources_coingecko.py` / `test_sources_worldbank.py` / `test_sources_akshare_cn.py`
- `warehouse/tests/test_sync_external.py`

### 2.2 DDL 变更（追加到现有分层文件，均幂等）

- `models/02_ods.sql`：新增 `ods_sec_submissions`、`ods_sec_facts`、`ods_crypto_meta`、`ods_macro_indicators`、`ods_cn_financials`、`ods_cn_lhb`
- `models/03_dwd.sql`：新增 `dim_indicator`、`fact_indicator`
- `models/04_dws.sql`：新增 `dws_indicator_daily` 物化视图

### 2.3 水位线

复用现有 `etl_watermarks` 表，scope 约定：

| 源 | scope 示例 |
|---|---|
| SEC submissions | `sec:cik:0000320193` |
| SEC facts | `sec:facts:0000320193` |
| CoinGecko | `coingecko:coin:bitcoin` |
| World Bank | `worldbank:series:NY.GDP.MKTP.CD` |
| akshare 财务 | `akshare:finance:600519` |
| akshare 龙虎榜 | `akshare:lhb:2026-08-23`（按上榜日） |

## 3. 数据模型

### 3.1 ODS 贴源表（按"数据源 × 数据域"分表，保留原始字段）

公共列：`raw_payload JSONB NOT NULL DEFAULT '{}'`、`ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()`、`sync_batch_id TEXT NOT NULL`。

**`ods_sec_submissions`**（每公司一行）

```sql
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
```

**`ods_sec_facts`**（每概念/期一行）

```sql
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
```

**`ods_crypto_meta`**（每币每快照日一行）

```sql
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
```

**`ods_macro_indicators`**（每国家/年一行）

```sql
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
```

**`ods_cn_financials`**（每报告期一行，宽表保留中文列名）

```sql
CREATE TABLE IF NOT EXISTS ods_cn_financials (
  symbol TEXT NOT NULL,
  report_date TEXT NOT NULL,
  indicator_name TEXT,
  indicator_value DOUBLE PRECISION,
  raw_payload JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_batch_id TEXT NOT NULL,
  PRIMARY KEY (symbol, report_date, indicator_name)
);
```

> 说明：akshare 财务摘要返回"报告期 × 指标列"宽表；为了 ODS 可查询与后续标准化，贴源层转成"报告期 × 指标名 × 指标值"长表存储（`indicator_name` 保留原始中文名），避免动态宽列。

**`ods_cn_lhb`**（每上榜日/股一行）

```sql
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

> 说明：龙虎榜同日同一股票可能因不同原因（日涨幅榜/换手榜等）多行上榜，故唯一键包含 `reason`。

### 3.2 DWD 通用指标模型

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

指标映射：

| 源 | indicator source | source_key 示例 | ref_key | as_of_date |
|---|---|---|---|---|
| SEC facts | `sec` | `us-gaap/NetIncomeLoss` | CIK | period_end |
| CoinGecko | `crypto` | `market_cap` / `current_price` | coin_id | snapshot_date |
| World Bank | `macro` | `NY.GDP.MKTP.CD` | country_code | date（年份） |
| akshare 财务 | `cn-finance` | `净利润` | A股代码 | 报告期 |
| akshare 龙虎榜 | `cn-lhb` | `close_price` / `change_pct` | A股代码 | 上榜日 |

### 3.3 DWS 汇总

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS dws_indicator_daily AS
SELECT indicator_id, ref_key, as_of_date, value
FROM fact_indicator;
```

> 说明：第一期 DWS 先做"最新值视图"语义的物化视图，随着数据积累再按需加窗口聚合（如近 N 日均值）。

## 4. 错误处理

- 每源独立事务：一个源失败只回滚自身，不推进该源水位线；其他源继续。
- 网络/解析失败：`try/except` 捕获记 warning，单源跳过；能拿到的原始响应进 `raw_payload`。
- 部分行失败：批内异常回滚该源事务（沿用现有 `upsert_ods_rows` 批次模式）。
- SEC 请求带显式 User-Agent：`finresearch-warehouse/1.0 (warehouse.etl@finresearch.local)`，否则会被 403。
- akshare 接口变动收敛在 `sources/akshare_cn.py` 一处。

## 5. 测试策略（TDD）

- 解析函数单测：用实测抓取的真实响应片段做 fixture，断言标准 dict 输出，不依赖网络。
- 装载测试：验证 ODS upsert、`dim_indicator`/`fact_indicator` 幂等写入（复用现有 PostgreSQL fixture 模式）。
- 增量/回滚测试：首次全量、二次只新增、失败回滚不推进水位线（沿用 `tests/test_sync_incremental.py` 模式）。
- 端到端：完成后跑一次真实网络同步，确认落库数据量。

## 6. 依赖与运行

- `warehouse/requirements.txt` 增加 `akshare>=1.18`（其余源用标准库 `urllib`）。
- 新增入口：`python -m etl.sync_external`，与 `sync_incremental`（K线/新闻）并列。
- README cron 示例更新为依次运行两个命令。
