# Global Finance Research Terminal

面向全球投资标的筛选的 Web MVP，覆盖 A 股、基金、美股、韩股、港股、外汇与数字货币。系统提供 K 线/价格趋势图、技术指标分析、综合筛选评分，以及宏观与国际局势面板。

## 功能

- 全球市场切换：A 股、基金、美股、韩股、港股、外汇、数字货币。
- 标的池：内置各市场代表性标的，代码集中在 `backend/core/universe.py`。
- K 线图：日/周/小时周期，包含 MA、成交量、缩放与十字光标。
- 指标分析：均线、MACD、RSI、布林带、ATR、波动率、动量。
- 智能筛选：综合趋势、动能、波动、风险与宏观因子，输出 0-100 评分。
- 今日推荐：首页跨市场推荐 10 支具体标的，覆盖股票、基金、外汇对和数字货币对。
- 推荐解释：点击标的展开加权推荐原因，涵盖技术指标、宏观分析、地缘政治、资金流向、政策与行业事件。
- 宏观面板：美元指数、美债收益率、原油、VIX 等快照，以及国际局势新闻热词。

## 架构

```text
frontend/  React + Vite + ECharts
backend/   FastAPI + yfinance + 可选 akshare/ccxt
```

数据层通过 `backend/core/providers.py` 提供统一入口：

- A 股、美股、港股、ETF 基金优先使用腾讯公开行情接口。
- 韩股优先使用 Naver Finance 公开行情接口。
- 数字货币优先使用 Gate.io 公开行情接口。
- 外汇日线优先使用 Frankfurter 公开汇率接口。
- 场外基金优先使用东方财富历史净值接口。
- `yfinance` 与 `akshare` 作为备用源。
- 任何数据源不可用时自动回退到确定性模拟数据，保证界面始终可演示。

## 数据真实性与依赖

- 首页 10 支推荐列表与点击后的 K 线分析均优先使用真实行情，并带 5 分钟内存缓存。
- 页面顶部的“实时行情/模拟数据”标识反映本次请求实际结果。
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
- `GET /api/analyze?market=us&symbol=AAPL` 单标的指标与评分。
- `GET /api/recommendations?limit=10` 首页加权推荐列表。
- `GET /api/screen?market=all&min_score=60&limit=60` 全球筛选。
- `GET /api/macro` 宏观快照与局势热词。

## 后续路线

- 接入更多开源数据源与历史数据缓存。
- 加入宏观新闻 RSS 抓取与情绪量化。
- 加入自定义指标、回测与组合管理。
- 将模拟数据切换为全量真实行情并做限流与授权设计。
