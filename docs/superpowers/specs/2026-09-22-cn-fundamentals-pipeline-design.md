# A股基本面指标采集设计（总资产 · 净资产 · 总市值 · 换手率）

> 日期：2026-09-22
> 状态：待评审
> 范围：warehouse 数仓补齐 A 股基本面字段并接入通用指标模型，同时修复外部源水位线缺陷
> 子项目：1 / 4（子项目 2 为 backend 端点，3 为选股因子，4 为前端展示）

## 1. 目标与范围

### 1.1 目标

补齐 11 字段清单中缺失的 4 个字段，并修复导致数据永不刷新的水位线缺陷：

- **新增新浪资产负债表源**：总资产、净资产(归母)、净资产(合计)
- **新增东财股本结构源**：总股本、流通股本
- **派生计算**（不新增采集）：换手率、总市值
- **修复水位线**：sec / worldbank / akshare-finance 三个源的「存在即跳过」缺陷
- **扩大采集范围**：A 股财务从硬编码 5 只扩到全市场 5565 只

### 1.2 不做的事

- 不接 backend API 层、不做选股因子、不做前端展示（分属子项目 2/3/4）
- 不改 K 线链路：换手率走通用指标模型，**不**写回 `ods_klines_a_share.turnover_rate`
- 不做流通市值，仅总市值
- 不修 coingecko 的 scope 增长问题（当前工作正常，仅是 `etl_watermarks` 行数增长）
- 不修 K 线全市场发现在东财快照不可用时的问题（见第 8 节"已知问题"）

### 1.3 背景：两个已确认的缺陷

**缺陷一：带单位数值被静默丢弃**（已在 commit `9c9a740` 修复）

同花顺财务摘要返回 `'445.17亿'`、`'-1.95%'` 形式的字符串，原实现直接 `float()` 失败后 `continue`，导致「净利润」「营业总收入」从未落库。同时 `float(False) == 0.0` 会把「科目缺失」误存为「0 元」。

**缺陷二：水位线永久跳过**（本设计修复）

`sync_external.py` 中 sec / worldbank / akshare-finance 的水位线 scope 不含时间粒度：

```python
scope = f"akshare:finance:{symbol}"        # 不含日期
if get_watermark(conn, scope) is not None:
    continue                                # 一旦设置，永久跳过
```

财务数据按季度更新，此逻辑等于「每只标的只在首次采集时取一次，此后永不刷新」。龙虎榜（`akshare:lhb`）与 K 线链路用的是正确的日期增量模式，coingecko 的 scope 含日期因而恰好可用。

## 2. 架构与数据流

```
新浪资产负债表 ─→ ods_cn_balance ──────────┐
东财股本结构   ─→ ods_cn_share_structure ──┼─→ build_indicators ─→ dim_indicator
                                          │                       fact_indicator
fact_kline ─┐                             │
            ├─→ build_daily_metrics ─→ ods_cn_daily_metrics ─┘
股本结构   ─┘
```

财务源按季度更新、股本变更极少，均为低频采集；换手率与总市值由 84 万行既有 K 线计算得出，**不新增日频采集**。

### 2.1 新增文件

| 文件 | 职责 |
|---|---|
| `warehouse/etl/sources/sina_cn.py` | 新浪资产负债表抓取与解析 |
| `warehouse/etl/sources/eastmoney_cn.py` | 东财股本结构抓取与解析 |
| `warehouse/etl/build_daily_metrics.py` | 由 K 线 + 股本计算换手率、总市值 |
| `warehouse/tests/test_sources_sina_cn.py` | 新浪源测试 |
| `warehouse/tests/test_sources_eastmoney_cn.py` | 东财源测试 |
| `warehouse/tests/test_build_daily_metrics.py` | 派生指标计算测试 |

### 2.2 修改文件

| 文件 | 变更 |
|---|---|
| `warehouse/models/02_ods.sql` | 追加 3 张 ODS 表（幂等） |
| `warehouse/etl/build_indicator.py` | `_iter_rows()` 增加 `cn-balance` / `cn-daily` 分支 |
| `warehouse/etl/sync_external.py` | 新增两个 sync 函数；修复水位线判据；per-symbol 容错 |
| `warehouse/tests/test_sync_external.py` | 扩展水位线与容错测试 |

## 3. 数据模型

### 3.1 ODS 贴源表

沿用 `ods_cn_financials` 的贴源模式（保留 `raw_payload` 与 `sync_batch_id`，主键去重保证幂等）。

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

### 3.2 通用指标映射

新增两个 `source`，复用既有 `dim_indicator` / `fact_indicator` 模型，**无需 DDL 变更**。

| source | source_key | name | unit | ref_key | as_of_date |
|---|---|---|---|---|---|
| `cn-balance` | `总资产` | 总资产 | CNY | symbol | 报告期 |
| `cn-balance` | `净资产(归母)` | 净资产(归母) | CNY | symbol | 报告期 |
| `cn-balance` | `净资产(合计)` | 净资产(合计) | CNY | symbol | 报告期 |
| `cn-daily` | `turnover_rate` | 换手率 | % | symbol | 交易日 |
| `cn-daily` | `market_cap` | 总市值 | CNY | symbol | 交易日 |

因为 `dim_indicator` 无模式约束，后续追加口径不需改表。

## 4. 指标计算

### 4.1 换手率

```
turnover_rate(%) = volume(手) × 10000 ÷ float_shares(股)
```

实测验证（600519，2026-09-21）：

| 来源 | 值 |
|---|---|
| 腾讯 volume | 25017 手 |
| 新浪 turnover | 0.0020012206（小数）|
| 本式结果 | 0.200123%（= 0.0020012 小数）|

**成立**，差异来自腾讯 volume 以「手」取整（相对误差 ~4e-6）。

单位约定：存量百分数（`0.200123` 表示 0.200123%），与 `ods_cn_financials` 中「净利润同比增长率」的约定一致。

**适用范围限制**：仅对 A 股成立。「volume 以手为单位」是 A 股行情特性，美股/港股/加密各有单位，不可套用。计算步骤需按 `market_id = 'a-share'` 过滤。

### 4.2 总市值

```
market_cap = close × total_shares
```

**关键约束**：`total_shares` 必须取 `change_date <= trade_date` 的最新一条，否则会用未来股本计算历史市值（如回购后的股本回填到回购前日期）。

### 4.3 执行位置与增量策略

`build_daily_metrics` 依赖 `fact_kline`，必须在 K 线同步**之后**运行。作为独立入口，与 `sync_daily` / `sync_external` 并列，结束时刷新 `dws_indicator_daily`（与 `sync_external` 结尾的既有做法一致）。

**增量策略**：以水位线 `cn-daily:metrics` 记录「最后已计算的交易日」，每次只处理 `trade_date > 水位线` 的行情，避免每日重算 84 万行。写入按 `(symbol, trade_date)` 主键 upsert，重复运行幂等。

**回填约束**：股本变更虽少，但**可能回填历史日期**（回购、增发等）。若本次股本同步写入的 `change_date` 早于 metrics 水位线，则将该水位线回退到 `change_date`，强制重算受影响区间。否则该区间的市值会沿用变更前的股本，形成静默错误——这正是本项目刚修复的同类问题（错误数值悄悄落库，而测试是绿的）。

## 5. 水位线设计（缺陷修复）

统一模式：**scope 稳定（不含时间），值存周期标识，判据为「值等于当前周期则跳过」**。

理由：若 scope 含时间（如 coingecko 那样），5565 只标的每日产生新 scope 行，`etl_watermarks` 会无限增长；scope 稳定则每只标的一行。

| 源 | scope | 值 | 周期 |
|---|---|---|---|
| 资产负债表 | `cn-balance:{symbol}` | ISO 周 `2026-W39` | 周 |
| 股本结构 | `cn-share:{symbol}` | ISO 周 | 周 |
| 财务摘要 | `akshare:finance:{symbol}` | ISO 周 | 周 |
| SEC | `sec:cik:{cik}` | ISO 周 | 周 |
| World Bank | `worldbank:series:{code}` | ISO 周 | 周 |
| 龙虎榜 | `akshare:lhb` | 日期 | 日（不变） |

周期选择依据：财务数据季度更新、World Bank 为年度数据，周粒度足以保证及时性。全市场周的采集成本约 100 分钟（财务摘要 33 min + 资产负债表 55 min + 股本结构 11 min）。

判据实现：

```python
scope = f"cn-balance:{symbol}"
if get_watermark(conn, scope) == current_iso_week():
    continue
# ... 采集 ...
set_watermark(conn, scope, current_iso_week())
```

**迁移行为（预期）**：现有水位线存的值是日期（如 `akshare:finance:600519` = `2026-09-22`），改动后判据变成 ISO 周（`2026-W39`），二者永不相等，因此**修复后的首次运行会全量重采一次**。这是刻意的——它同时消化掉此前因缺陷而未刷新的数据。此后按周增量。

## 6. 标的清单

财务采集需要全 A 股代码清单。K 线侧的全市场发现依赖东财 `stock_zh_a_spot_em`（当前不可用），因此本设计改用：

```python
ak.stock_info_a_code_name()   # 实测可用，返回 5565 只，耗时 5.5s
```

新浪接口需要带市场前缀的代码（`sh600519` / `sz000001`），转换规则：

| 首位 | 前缀 |
|---|---|
| 6、9 | `sh` |
| 0、3 | `sz` |
| 4、8 | 北交所，新浪不支持 → 由容错机制跳过并记录 |

## 7. 错误处理

| 场景 | 处理 |
|---|---|
| 单只标的全部请求失败 | 记日志 + 进失败清单，继续下一只（per-symbol 容错） |
| 整个源连接中断 | 保持既有语义：回滚该源，不阻塞其他源 |
| 科目缺失 | 跳过该指标行，**不写 0** |
| 格式异常（带单位/布尔/空） | 解析失败即跳过 |
| 股本记录为空 | 该标的不产出总市值与换手率，不写 0 |

**per-symbol 容错的必要性**：现有 `_run_source` 是整源单事务，首次全量约 65 分钟，中途一次网络抖动会导致已完成的数千只全部回滚。改为单只独立 try/except，失败进清单，返回统计中包含失败标的。

## 8. 测试策略（TDD）

一源一测试文件，按项目既有惯例使用 `monkeypatch` 替换网络调用。

**强制要求：fixture 必须使用真实响应形状。** 本项目刚发生过一次严重逃逸——测试用 `{"净利润": 862.3}`（纯 float），而真实响应是 `'445.17亿'`（带单位字符串），导致 bug 在测试全绿的情况下长期存在。因此新测试的 fixture 一律从实际接口响应中截取，包含：

- 新浪资产负债表的真实列名（注意 `所有者权益` 列实测为 NaN，须用 `所有者权益(或股东权益)合计`）
- 东财股本结构的真实中文列名与日期格式
- 同花顺的带单位字符串

测试覆盖：

1. 新浪资产负债表解析：真实形状、NaN 列处理、科目缺失
2. 东财股本结构解析：取最新变更记录、日期格式
3. 换手率计算：与新浪 turnover 的对照验证
4. 总市值计算：`change_date <= trade_date` 约束（含股本变更回填场景）
5. 水位线：同周跳过、跨周重采
6. 容错：单只失败不影响其余，失败清单正确返回

## 9. 验收标准

全部可独立验证，不依赖子项目 2/3/4：

1. `ods_cn_balance`、`ods_cn_share_structure`、`ods_cn_daily_metrics` 三表有真实数据
2. `fact_indicator` 中出现 总资产、净资产(归母)、净资产(合计)、总市值、换手率五个指标
3. 数值与源一致：600519 总资产 3090 亿、归母净资产 2512 亿、总市值约 1.57 万亿
4. **重复运行行为正确**：同一周内重跑跳过，跨周重采
5. 全市场覆盖：A 股标的数达到 5565 量级（失败的北交所标的记录在清单中）
6. 完整测试套件通过，无回归

## 10. 已知问题与后续

- **东财接口不可用范围**：`stock_zh_a_hist`（历史行情）、`stock_zh_a_spot_em`（全市场快照）、`stock_individual_info_em`（个股信息）当前均返回 `RemoteDisconnected`，仅 `stock_zh_a_gbjg_em`（股本结构）可用。这同时影响 K 线侧的全市场发现与 akshare 备用源，应在东财恢复后复测。
- **coingecko scope 增长**：其 scope 含日期，`etl_watermarks` 会持续增长。当前工作正常，未纳入本次修复。
- **换手率精度**：受「手」取整限制，相对误差 ~4e-6，对因子计算无影响。
- **后续子项目**：backend 端点（含 SQLite 回退路径的财务表缺失问题）、选股因子、前端展示。
