import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, RefreshCw, TrendingUp } from "lucide-react";
import KlineChart from "./components/KlineChart";
import MacroPanel from "./components/MacroPanel";
import ScreenerPanel, {
  type Filters,
} from "./components/ScreenerPanel";
import {
  fetchAnalysis,
  fetchKline,
  fetchMacro,
  fetchRecommendations,
  fetchScreen,
} from "./api";
import type {
  AnalysisData,
  KlineRow,
  MacroPayload,
  Period,
  ScreenItem,
  ScreenResult,
} from "./types";

const DEFAULT_FILTERS: Filters = {
  minScore: 45,
  minTrend: 0,
  minRsi: 20,
  maxRsi: 80,
  sortBy: "total_score",
};

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function signed(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--";
  }
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function scoreClass(score: number | null | undefined): string {
  if (score === null || score === undefined) {
    return "";
  }
  if (score >= 72) {
    return "score-high";
  }
  if (score >= 55) {
    return "score-mid";
  }
  return "score-low";
}

interface StatProps {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "accent";
  score?: number;
}

function Stat({ label, value, sub, tone, score }: StatProps) {
  return (
    <div className="stat-item">
      <span className="stat-label">{label}</span>
      <span className={`stat-value ${tone ?? ""} ${scoreClass(score)}`}>{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  );
}

export default function App() {
  const [market, setMarket] = useState("all");
  const [period, setPeriod] = useState<Period>("d");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [screenResult, setScreenResult] = useState<ScreenResult | null>(null);
  const [selected, setSelected] = useState<ScreenItem | null>(null);
  const [kline, setKline] = useState<KlineRow[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [macroData, setMacroData] = useState<MacroPayload | null>(null);
  const [source, setSource] = useState<"live" | "mock">("mock");
  const [loading, setLoading] = useState({
    screen: false,
    chart: false,
    macro: false,
  });
  const [error, setError] = useState("");
  const filtersRef = useRef(filters);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const applyListResult = useCallback((result: ScreenResult) => {
    setScreenResult(result);
    setSelected((previous) => {
      if (
        previous &&
        result.items.some(
          (item) =>
            item.symbol === previous.symbol && item.market === previous.market,
        )
      ) {
        return previous;
      }
      return result.items[0] ?? null;
    });
  }, []);

  const runScreen = useCallback(async () => {
    const current = filtersRef.current;
    setLoading((previous) => ({ ...previous, screen: true }));
    setError("");
    try {
      const result = await fetchScreen({
        market,
        minScore: current.minScore,
        minTrend: current.minTrend,
        minRsi: current.minRsi,
        maxRsi: current.maxRsi,
        sortBy: current.sortBy,
        limit: 30,
      });
      applyListResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "筛选请求失败");
    } finally {
      setLoading((previous) => ({ ...previous, screen: false }));
    }
  }, [market, applyListResult]);

  const runRecommendations = useCallback(async () => {
    setLoading((previous) => ({ ...previous, screen: true }));
    setError("");
    try {
      const result = await fetchRecommendations(10);
      applyListResult(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "推荐列表请求失败");
    } finally {
      setLoading((previous) => ({ ...previous, screen: false }));
    }
  }, [applyListResult]);

  const runMacro = useCallback(async () => {
    setLoading((previous) => ({ ...previous, macro: true }));
    try {
      setMacroData(await fetchMacro());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "宏观数据请求失败");
    } finally {
      setLoading((previous) => ({ ...previous, macro: false }));
    }
  }, []);

  useEffect(() => {
    if (market === "all") {
      void runRecommendations();
    } else {
      void runScreen();
    }
    void runMacro();
  }, [market, runRecommendations, runScreen, runMacro]);

  useEffect(() => {
    if (!selected) {
      setKline([]);
      setAnalysis(null);
      return;
    }
    let cancelled = false;
    setLoading((previous) => ({ ...previous, chart: true }));
    Promise.all([
      fetchKline(selected.market, selected.symbol, period),
      fetchAnalysis(selected.market, selected.symbol),
    ])
      .then(([klineResponse, analysisResponse]) => {
        if (cancelled) {
          return;
        }
        setKline(klineResponse.items);
        setSource(klineResponse.source);
        setAnalysis(analysisResponse.analysis);
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "图表数据请求失败");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading((previous) => ({ ...previous, chart: false }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected, period]);

  const refreshChart = useCallback(() => {
    if (!selected) {
      return;
    }
    setLoading((previous) => ({ ...previous, chart: true }));
    Promise.all([
      fetchKline(selected.market, selected.symbol, period),
      fetchAnalysis(selected.market, selected.symbol),
    ])
      .then(([klineResponse, analysisResponse]) => {
        setKline(klineResponse.items);
        setSource(klineResponse.source);
        setAnalysis(analysisResponse.analysis);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : "图表刷新失败");
      })
      .finally(() => {
        setLoading((previous) => ({ ...previous, chart: false }));
      });
  }, [selected, period]);

  const handleRefreshAll = useCallback(() => {
    if (market === "all") {
      void runRecommendations();
    } else {
      void runScreen();
    }
    void runMacro();
    if (selected) {
      void refreshChart();
    }
  }, [market, runScreen, runRecommendations, runMacro, refreshChart, selected]);

  const detailItems = useMemo(() => {
    if (!analysis) {
      return [];
    }
    return [
      { label: "5 日涨跌", value: `${signed(analysis.change_5d)}%` },
      { label: "20 日涨跌", value: `${signed(analysis.change_20d)}%` },
      { label: "60 日涨跌", value: `${signed(analysis.change_60d)}%` },
      { label: "ATR %", value: `${formatNumber(analysis.atr_pct)}%` },
      { label: "布林带宽", value: formatNumber(analysis.boll.bandwidth, 3) },
      { label: "MA5 / MA20", value: `${formatNumber(analysis.sma5)} / ${formatNumber(analysis.sma20)}` },
      { label: "MACD 柱", value: formatNumber(analysis.macd_hist, 3) },
      { label: "年化波动", value: `${formatNumber(analysis.volatility20, 3)}` },
    ];
  }, [analysis]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <TrendingUp size={18} />
          <span>全球投研终端</span>
          <em>Global Macro Screener</em>
        </div>
        <div className="header-status">
          <span className={`source-pill ${source}`}>
            {source === "live" ? "实时行情" : "模拟数据"}
          </span>
          <span className="universe-count">
            {macroData?.universe_size ?? 28} 个标的
          </span>
          <button className="icon-btn" title="刷新全部数据" onClick={handleRefreshAll}>
            <RefreshCw size={15} />
          </button>
        </div>
      </header>

      {error && (
        <div className="error-bar">
          <span>{error}</span>
          <button onClick={() => setError("")}>关闭</button>
        </div>
      )}

      <main className="workspace">
        <ScreenerPanel
          market={market}
          mode={market === "all" ? "recommend" : "screen"}
          onMarketChange={(nextMarket) => setMarket(nextMarket)}
          result={screenResult}
          selected={selected}
          onSelect={(item) => setSelected(item)}
          filters={filters}
          onFiltersChange={setFilters}
          onApply={() => void runScreen()}
          onRefresh={
            market === "all" ? () => void runRecommendations() : () => void runScreen()
          }
          loading={loading.screen}
        />

        <section className="panel chart-panel">
          <div className="panel-head chart-head">
            <div className="chart-title">
              <h2>{selected?.name ?? "选择标的"}</h2>
              <span>
                {selected
                  ? `${selected.symbol} · ${selected.market_name} · ${selected.sector}`
                  : "从左侧选择候选标的"}
              </span>
            </div>
            <div className="chart-toolbar">
              <div className="segmented" role="tablist" aria-label="周期">
                {(["d", "w", "h"] as Period[]).map((value) => (
                  <button
                    key={value}
                    role="tab"
                    aria-selected={period === value}
                    className={period === value ? "active" : ""}
                    onClick={() => setPeriod(value)}
                  >
                    {value === "d" ? "日" : value === "w" ? "周" : "小时"}
                  </button>
                ))}
              </div>
              <button className="icon-btn" title="刷新图表" onClick={refreshChart}>
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          <div className="chart-summary">
            <Stat
              label="最新价"
              value={formatNumber(analysis?.price)}
              sub={`${signed(analysis?.change_1d)}% 当日`}
              tone={analysis && analysis.change_1d >= 0 ? "up" : "down"}
            />
            <Stat
              label="RSI 14"
              value={formatNumber(analysis?.rsi14, 1)}
              sub={analysis ? (analysis.rsi14 ?? 0) > 65 ? "偏热" : "正常" : ""}
            />
            <Stat
              label="MACD 柱"
              value={formatNumber(analysis?.macd_hist, 3)}
              sub={analysis ? (analysis.macd_hist ?? 0) >= 0 ? "多头" : "空头" : ""}
              tone={analysis && (analysis.macd_hist ?? 0) >= 0 ? "up" : "down"}
            />
            <Stat
              label="20 日波动"
              value={formatNumber(analysis?.volatility20, 3)}
              sub={analysis ? "年化" : ""}
            />
            <Stat
              label="趋势分"
              value={formatNumber(analysis?.trend_score, 0)}
              score={analysis?.trend_score}
            />
            <Stat
              label="综合评分"
              value={formatNumber(analysis?.total_score, 0)}
              sub={analysis ? "技术 + 宏观" : ""}
              score={analysis?.total_score}
            />
          </div>

          <div className="chart-wrap">
            {loading.chart && kline.length === 0 ? (
              <div className="chart-loading">
                <Activity size={18} />
                <span>正在加载行情...</span>
              </div>
            ) : (
              <KlineChart rows={kline} period={period} />
            )}
          </div>

          <div className="detail-strip">
            {detailItems.map((item) => (
              <div className="detail-item" key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>

          <div className="signal-strip">
            {analysis?.signals.map((signal) => (
              <span className="signal-chip" key={signal}>
                {signal}
              </span>
            ))}
            {analysis && analysis.signals.length === 0 && (
              <span className="signal-chip muted">信号未触发</span>
            )}
          </div>
        </section>

        <MacroPanel data={macroData} loading={loading.macro} />
      </main>
    </div>
  );
}
