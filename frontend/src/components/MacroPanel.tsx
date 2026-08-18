import { Globe2, Newspaper } from "lucide-react";
import type { MacroPayload } from "../types";

const MARKET_LABELS: Record<string, string> = {
  "a-share": "A股",
  fund: "基金",
  us: "美股",
  kr: "韩股",
  hk: "港股",
  fx: "外汇",
  crypto: "数字货币",
};

interface MacroPanelProps {
  data: MacroPayload | null;
  loading: boolean;
}

export default function MacroPanel({ data, loading }: MacroPanelProps) {
  const biases = data?.bias ? Object.entries(data.bias) : [];
  return (
    <aside className="panel macro-panel">
      <div className="panel-head">
        <Globe2 className="icon" size={15} />
        <h2>宏观与局势</h2>
        <span className={`mode-pill ${data?.mode === "live" ? "live" : ""}`}>
          {data?.mode === "live" ? "实时" : "快照"}
        </span>
      </div>

      <div className="macro-grid">
        {loading && !data
          ? Array.from({ length: 8 }, (_, index) => (
              <div className="skeleton-box" key={index} />
            ))
          : data?.snapshot.map((item) => (
              <div className="macro-item" key={item.key}>
                <span className="macro-name">{item.name}</span>
                <span className="macro-value">{item.value}</span>
                <span className={`macro-change ${item.direction}`}>
                  {item.change}
                </span>
              </div>
            ))}
      </div>

      <div className="macro-section">
        <h3>市场宏观偏置</h3>
        <div className="bias-list">
          {biases.map(([market, bias]) => (
            <div className="bias-item" key={market}>
              <span className="bias-market">{MARKET_LABELS[market] ?? market}</span>
              <span className={`bias-dot ${bias.direction}`} />
              <span className="bias-label">{bias.label}</span>
              <span className="bias-score">{bias.score}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="macro-section news-section">
        <div className="section-title">
          <Newspaper size={13} />
          <h3>局势热讯</h3>
        </div>
        <div className="news-list">
          {data?.news.map((item, index) => (
            <article className="news-item" key={`${item.title}-${index}`}>
              <div className="news-meta">
                <span>{item.time}</span>
                <span>{item.source}</span>
              </div>
              <p>{item.title}</p>
              <div className="news-tags">
                {item.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </div>
    </aside>
  );
}
