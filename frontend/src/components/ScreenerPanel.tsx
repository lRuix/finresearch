import { useState } from "react";
import { Filter, RefreshCw, Search, Sparkles } from "lucide-react";
import type { ScreenItem, ScreenResult } from "../types";

export const MARKET_TABS = [
  { id: "all", name: "全球" },
  { id: "a-share", name: "A股" },
  { id: "fund", name: "基金" },
  { id: "us", name: "美股" },
  { id: "kr", name: "韩股" },
  { id: "hk", name: "港股" },
  { id: "fx", name: "外汇" },
  { id: "crypto", name: "数字货币" },
];

export interface Filters {
  minScore: number;
  minTrend: number;
  minRsi: number;
  maxRsi: number;
  sortBy: string;
}

interface ScreenerPanelProps {
  market: string;
  mode: "recommend" | "screen";
  onMarketChange: (market: string) => void;
  result: ScreenResult | null;
  selected: ScreenItem | null;
  onSelect: (item: ScreenItem) => void;
  filters: Filters;
  onFiltersChange: (filters: Filters) => void;
  onApply: () => void;
  onRefresh: () => void;
  loading: boolean;
  onSearch?: (query: string) => void;
}

function signed(value: number): string {
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

export default function ScreenerPanel({
  market,
  mode,
  onMarketChange,
  result,
  selected,
  onSelect,
  filters,
  onFiltersChange,
  onApply,
  onRefresh,
  loading,
  onSearch,
}: ScreenerPanelProps) {
  const [searchText, setSearchText] = useState("");
  return (
    <aside className="panel screener-panel">
      <div className="panel-head">
        <Filter className="icon" size={15} />
        <h2>{mode === "recommend" ? "今日推荐" : "标的筛选"}</h2>
        <button className="icon-btn" title="刷新筛选" onClick={onRefresh}>
          <RefreshCw size={14} />
        </button>
      </div>

      <div className="screener-search">
        <input
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && onSearch) onSearch(searchText.trim());
          }}
          placeholder="输入代码搜索任意标的（如 688836 / AAPL / BTCUSDT）"
        />
        <button onClick={() => onSearch?.(searchText.trim())}>搜索</button>
      </div>

      <div className="market-tabs" role="tablist" aria-label="市场">
        {MARKET_TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={market === tab.id}
            className={market === tab.id ? "active" : ""}
            onClick={() => onMarketChange(tab.id)}
          >
            {tab.name}
          </button>
        ))}
      </div>

      <div className="filter-block">
        <label className="range-label">
          <span>综合分下限</span>
          <output>{filters.minScore}</output>
        </label>
        <input
          type="range"
          min="0"
          max="90"
          step="5"
          value={filters.minScore}
          onChange={(event) =>
            onFiltersChange({ ...filters, minScore: Number(event.target.value) })
          }
        />
        <label className="range-label">
          <span>趋势分下限</span>
          <output>{filters.minTrend}</output>
        </label>
        <input
          type="range"
          min="0"
          max="100"
          step="10"
          value={filters.minTrend}
          onChange={(event) =>
            onFiltersChange({ ...filters, minTrend: Number(event.target.value) })
          }
        />
        <div className="rsi-row">
          <label>
            <span>RSI 区间</span>
            <span className="rsi-inputs">
              <input
                type="number"
                min="0"
                max="100"
                value={filters.minRsi}
                onChange={(event) =>
                  onFiltersChange({ ...filters, minRsi: Number(event.target.value) })
                }
              />
              <em>-</em>
              <input
                type="number"
                min="0"
                max="100"
                value={filters.maxRsi}
                onChange={(event) =>
                  onFiltersChange({ ...filters, maxRsi: Number(event.target.value) })
                }
              />
            </span>
          </label>
        </div>
        <label className="select-label">
          <span>排序方式</span>
          <select
            value={filters.sortBy}
            onChange={(event) =>
              onFiltersChange({ ...filters, sortBy: event.target.value })
            }
          >
            <option value="total_score">综合评分</option>
            <option value="change_20d">20 日涨幅</option>
            <option value="rsi14">RSI 强度</option>
            <option value="trend_score">趋势分</option>
          </select>
        </label>
        <button className="primary-btn" onClick={onApply} disabled={loading}>
          <Search size={14} />
          {loading ? "筛选中..." : "运行筛选"}
        </button>
      </div>

      <div className="list-head">
        <span>{mode === "recommend" ? "推荐标的" : "候选标的"}</span>
        <span>
          {result?.count ?? 0} {mode === "recommend" ? "支" : "项"}
        </span>
      </div>
      <div className="symbol-list">
        {loading && !result
          ? Array.from({ length: 6 }, (_, index) => (
              <div className="skeleton-row" key={index} />
            ))
          : result?.items.map((item) => {
              const active =
                selected?.symbol === item.symbol && selected?.market === item.market;
              return (
                <div
                  key={`${item.market}-${item.symbol}`}
                  className="symbol-card"
                >
                  <button
                    className={`symbol-item ${active ? "active" : ""}`}
                    onClick={() => onSelect(item)}
                  >
                    <div className="sym-row">
                      <span className="sym-name">{item.name}</span>
                      <span
                        className={`sym-change ${item.change_1d >= 0 ? "up" : "down"}`}
                      >
                        {signed(item.change_1d)}%
                      </span>
                    </div>
                    <div className="sym-row">
                      <span className="asset-type">{item.asset_type}</span>
                      <span className="sym-code">
                        {item.symbol} · {item.market_name}
                      </span>
                      <span className="score-pill">
                        {item.total_score.toFixed(0)}
                      </span>
                    </div>
                    <div className="sym-signals">
                      {item.signals.slice(0, 2).map((signal) => (
                        <span key={signal}>{signal}</span>
                      ))}
                    </div>
                  </button>

                  {active && (
                    <div className="reason-expand">
                      <div className="reason-head">
                        <Sparkles size={12} />
                        <span>推荐原因</span>
                        <em>按权重排序</em>
                      </div>
                      {(item.reasons ?? []).map((reason, index) => (
                        <div
                          className={`reason-item ${reason.type}`}
                          key={`${reason.title}-${index}`}
                        >
                          <div className="reason-top">
                            <span className="reason-rank">{index + 1}</span>
                            <span className="reason-type">{reason.label}</span>
                            <span className="reason-weight">{reason.weight}</span>
                          </div>
                          <strong>{reason.title}</strong>
                          <p>{reason.detail}</p>
                          <div className="weight-track">
                            <span style={{ width: `${reason.weight}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
      </div>
    </aside>
  );
}
