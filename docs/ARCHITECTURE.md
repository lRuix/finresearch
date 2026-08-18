# Global Finance Research Terminal — 系统架构图

> 基于当前代码（`backend/` + `frontend/`）生成的架构说明，与实现同步。

## 总体架构

```mermaid
flowchart TB
    subgraph Browser["浏览器 (http://localhost:5173)"]
        UI["React SPA<br/>main.tsx → App.tsx"]
        SC["ScreenerPanel<br/>筛选 / 推荐列表"]
        KC["KlineChart<br/>ECharts K线 / MA / 成交量"]
        MP["MacroPanel<br/>宏观快照 / 局势热词"]
        API["api.ts<br/>fetch 封装"]
    end

    subgraph Frontend["frontend/ — React + TypeScript + Vite + ECharts"]
        UI --> SC
        UI --> KC
        UI --> MP
        UI --> API
        TYPES["types.ts<br/>共享类型定义"]
        UI -.-> TYPES
    end

    subgraph Backend["backend/ — FastAPI + Uvicorn (端口 8000)"]
        APP["app.py<br/>FastAPI 路由 + CORS"]
        H["/api/health"]
        M["/api/markets"]
        U["/api/universe"]
        K["/api/kline"]
        A["/api/analyze"]
        S["/api/screen"]
        R["/api/recommendations"]
        MC["/api/macro"]
    end

    subgraph Core["backend/core/ — 业务逻辑"]
        UNIV["universe.py<br/>市场与标的池"]
        PROV["providers.py<br/>数据提供层 + 5min缓存 + 熔断"]
        IND["indicators.py<br/>均线/MACD/RSI/布林/ATR/动量"]
        SCR["screener.py<br/>多因子评分 0-100"]
        MAC["macro.py<br/>宏观快照 / 新闻 / 市场偏置"]
    end

    subgraph Sources["外部数据源（真实行情，失败自动回退）"]
        TX["腾讯行情<br/>A股 / 美股 / 港股 / ETF"]
        NV["Naver Finance<br/>韩股"]
        GT["Gate.io<br/>数字货币"]
        BN["Binance<br/>数字货币备用"]
        FR["Frankfurter<br/>外汇日线"]
        EM["东方财富<br/>场外基金净值"]
        YF["yfinance<br/>通用备用"]
        AK["akshare<br/>A股/基金备用"]
        MOCK["确定性模拟数据<br/>最终兜底"]
    end

    API -- "HTTP GET /api/*" --> APP
    APP --> H & M & U & K & A & S & R & MC
    M & U --> UNIV
    K --> PROV
    A --> IND
    A --> MAC
    S --> SCR
    R --> SCR
    MC --> MAC
    SCR --> IND
    SCR --> MAC
    SCR --> UNIV
    IND --> PROV
    PROV --> TX & NV & GT & BN & FR & EM & YF & AK & MOCK
```

## 请求数据流

```mermaid
sequenceDiagram
    participant U as 用户
    participant F as 前端 App.tsx
    participant A as FastAPI app.py
    participant P as providers.py
    participant I as indicators.py
    participant X as 外部数据源

    U->>F: 选择市场 / 点击标的
    alt 市场 = all（首页）
        F->>A: GET /api/recommendations
        A->>P: screener.recommend()
        P->>X: 拉取真实行情（腾讯/Naver/Gate/Frankfurter…）
        X-->>P: 行情数据（失败则回退下一源）
        P-->>A: K线 + source 标识
        A-->>F: 推荐列表 + 加权原因
    else 指定市场
        F->>A: GET /api/screen?market=us&min_score=60
        A->>P: screener.screen()（并发分析）
        P-->>A: 评分结果
        A-->>F: 筛选列表
    end

    F->>A: GET /api/kline + GET /api/analyze
    A->>P: get_kline_with_source()
    P->>X: 按市场路由到主源
    X-->>P: K线
    P-->>A: rows + source ("live"/"mock")
    A->>I: analyze(rows, meta)
    I-->>A: 指标 + 综合评分 + 信号
    A->>MAC: macro_score_for(market)
    A-->>F: 图表数据 + 分析结果
```

## 关键设计

| 关注点 | 实现 |
|---|---|
| **多市场路由** | `providers.py` 按市场选择主源：A股/美股/港股→腾讯，韩股→Naver，数字货币→Gate.io，外汇→Frankfurter，场外基金→东方财富 |
| **高可用降级** | 主源失败 → 备用源（yfinance/akshare/Binance）→ 确定性模拟数据，`source` 字段标识 `live`/`mock` |
| **性能** | 5 分钟内存缓存（线程安全锁）+ 失败源 120 秒熔断（`_dead_providers`） |
| **评分模型** | `indicators.py` 计算技术指标 → `screener.py` 综合趋势/动能/波动/风险/宏观因子 → 0-100 分 |
| **推荐解释** | 每个标的附加权原因（技术指标/宏观/地缘/资金流/政策/行业/风险） |
| **CORS** | FastAPI 全放开，便于前端 5173 ↔ 后端 8000 跨端口调试 |

## 启动拓扑

```text
┌─────────────┐   HTTP/JSON   ┌──────────────┐   HTTPS    ┌──────────────────┐
│ Vite dev    │ ────────────▶ │ FastAPI      │ ─────────▶ │ 腾讯/Naver/Gate/  │
│ :5173       │               │ :8000        │            │ Frankfurter/东财  │
└─────────────┘               └──────────────┘            └──────────────────┘
```

- 后端：`python -m uvicorn app:app --reload --port 8000`
- 前端：`pnpm dev` → `http://localhost:5173`
