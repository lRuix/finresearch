# Global Finance Research Terminal

面向全球投资标的筛选的 Web MVP，覆盖 A 股、基金、美股、韩股、港股、外汇与数字货币。系统提供 K 线/价格趋势图、技术指标分析、综合筛选评分，以及宏观与国际局势面板。

## 功能

- 全球市场切换：A 股、基金、美股、韩股、港股、外汇、数字货币。
- 标的池：基础标的中内置池集中在 `backend/domain/universe_data.py`，外汇候选另有 provider 静态列表。
- 任意代码搜索：跨市场识别 A 股、基金、美股、韩股、港股、外汇与数字货币代码，搜索后可直接打开 K 线与指标分析。
- K 线图：日/周/小时周期，包含 MA、成交量、缩放与十字光标。
- 指标分析：均线、MACD、RSI、布林带、ATR、波动率、动量。
- 智能筛选：综合趋势、动能、波动、风险与宏观因子，输出 0-100 评分。
- 今日推荐：首页跨市场推荐 10 支具体标的；候选池默认从全市场拉取（A 股、港股、场内 ETF 与加密按成交额/流动性取前 20 只，外汇使用 provider 静态列表，其余市场回退内置池），数据源失败时回退内置池。
- 推荐解释：点击标的展开加权推荐原因，涵盖技术指标、宏观分析、地缘政治、资金流向、政策与行业事件。
- 宏观面板：美元指数、美债收益率、原油、VIX 等快照，以及国际局势新闻热词。

## 架构

项目采用依赖倒置的分层单体，四层依赖方向严格向下：

```text
frontend/        React + Vite + ECharts
backend/
├── presentation/   展示层：FastAPI 路由、Pydantic 请求校验与兼容响应
├── application/    应用编排层：用例服务与端口定义
├── domain/         领域/算法层：纯值对象、指标、估值与算法
└── infrastructure/ 基础设施层：外部数据源适配器、SQLite 仓库、宏观数据提供
```

- **展示层** `backend/presentation/`：`api/routes.py` 只做参数校验、调用应用服务、返回兼容响应；顶层 `app.py` 是装配根，负责 `build_container()` 组装依赖并注册路由。
- **应用层** `backend/application/`：`ports.py` 定义 `MarketDataRepository`、`MarketDataSource`、`FxRateProvider`、`MacroNewsProvider` 端口；`services/` 包含分析、筛选、推荐、比较、同步、搜索、目录与宏观服务，负责把数据、算法和约束编排成用例。
- **领域/算法层** `backend/domain/`：`models.py` 定义 `Instrument`/`KlineRow` 值对象；`indicators.py`、`valuation/`、`universe_data.py` 与 `algorithms/`（因子/情绪/引擎）均为纯逻辑，不 import 数据源、数据库或 HTTP。
- **基础设施层** `backend/infrastructure/`：`datasources/` 实现真实数据源路由、熔断、内存缓存与确定性模拟兜底；`repository/postgres.py` 提供数仓 PostgreSQL 仓库（读取 `fact_kline` 行情、`backend_evaluations` 推荐缓存等），`repository/sqlite.py` 为默认本地仓库（未配置数仓时使用）。

`backend/core/` 兼容层已移除。应用服务通过端口使用基础设施实现，数据仓库、算法层与前端界面可以分别替换或独立演进。

### 数据读写路径

- 设置 `WAREHOUSE_DSN` 环境变量后，应用服务从数仓 PostgreSQL 读取 K 线（`fact_kline`）与推荐缓存（`backend_evaluations`），前端数据全部来自数仓；未设置时回退 SQLite 本地仓库。
- backend 不再提供运行时行情同步：数据由数仓每日 ETL（`sync_incremental` / `sync_external`）维护，查询缺数据时直接返回已有数据。
- 数据源路由位于 `backend/infrastructure/datasources/provider_impl.py`：A 股/美股/港股/ETF 优先腾讯公开行情，韩股优先 Naver，数字货币优先 Gate.io，外汇优先 Frankfurter，场外基金优先东方财富；`yfinance` 与 `akshare` 作为备用源。
- 外部行情带 5 分钟内存缓存与 120 秒失败熔断；全市场候选按市场缓存 1 小时，兜底结果缓存 60 秒；首页推荐结果按自然日缓存到 SQLite。
- 任何数据源不可用时自动回退到确定性模拟数据，保证界面始终可演示。

## 数据真实性与依赖

- 首页 10 支推荐列表与点击后的 K 线分析数据来自数仓 PostgreSQL（配置 `WAREHOUSE_DSN` 时）或 SQLite 本地仓库（默认）；数据由数仓 ETL 每日更新，推荐结果按自然日写入 `backend_evaluations`（数仓模式）或 SQLite `evaluations`（默认模式）。
- 页面顶部标识按 `source` 显示：`live` 显示实时行情，`local`/`mock` 当前显示为模拟数据。
- 真实数据需要满足两个条件：安装对应 Python 依赖，并保证运行环境可以访问数据源网络。
- 当前已验证的真实主源：腾讯行情、Naver Finance、Gate.io、Frankfurter、东方财富基金净值。
- `yfinance` 与 `akshare` 已安装并作为备用源；数字货币备用源为 Binance。
- 宏观快照默认使用内置缓存，新闻实时 RSS 抓取为可选能力。

## 启动

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

默认使用 SQLite 本地仓库。要让前端全部从数仓读取数据，启动前设置：

```bash
export WAREHOUSE_DSN="postgresql://warehouse:warehouse@127.0.0.1:5432/warehouse"
```

前端：

```bash
cd frontend
pnpm install
pnpm dev
```

访问 `http://localhost:5173`。

## API 概览

- `GET /api/markets` 市场列表。
- `GET /api/universe?market=all` 标的池。
- `GET /api/kline?market=us&symbol=AAPL&period=d&limit=180` K 线数据。
- `GET /api/analyze?market=us&symbol=AAPL` 任意代码的单标的指标与评分。
- `GET /api/recommendations?limit=10&candidates_per_market=20` 首页加权推荐列表；`candidates_per_market=0` 时回退内置标的池。
- `GET /api/screen?market=all&min_score=60&limit=60` 全球筛选。
- `GET /api/macro` 宏观快照与局势热词。
- `GET /api/search?q=688836` 任意代码跨市场搜索。
- `GET /api/recommend?market=a-share&symbol=688836` 单标的加权推荐（因子分 + 情绪 + 综合评分）。
- `GET /api/compare?symbols=AAPL,600519,BTCUSDT` 跨资产风险调整后收益排序。

## 跨资产 RMB 计价与缓存

- 比较路径的 RMB 折算按参考汇率直接缩放收盘价（`domain/valuation/currency.py` 的 `to_rmb_closes`）；`to_rmb_returns` 同时提供含汇率变动的复合公式，当前未接入比较路径。
- 首页推荐结果按**自然日**缓存，写入数仓 `backend_evaluations` 表（`WAREHOUSE_DSN` 模式）或 SQLite `evaluations` 表（默认模式），同一键同一天只评估一次。
- 购汇约束：美股/港股/韩股/外汇/数字货币需占用个人年度等值 5 万美元购汇额度（`domain/valuation/constraints.py`，`requires_quota`/`quota_note`）。

## 全市场推荐说明

- 首页推荐结果按自然日缓存到 SQLite，同一天重复请求不会全量重算；全市场候选池按市场内存缓存 1 小时（兜底 60 秒）。
- A 股、港股、场内 ETF 与加密会动态拉取全市场快照并按成交额/流动性取前 N 只；外汇使用 provider 静态主要货币对列表。
- 美股与韩股目前没有可免费获取的公开全量列表，仍使用内置代表性标的；场外基金暂未纳入动态候选池。

## 后续路线

- 接入更多开源数据源与历史数据缓存。
- 加入宏观新闻 RSS 抓取与情绪量化。
- 加入自定义指标、回测与组合管理。
- 将模拟数据切换为全量真实行情并做限流与授权设计。
