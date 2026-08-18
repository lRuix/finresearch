export type Period = "d" | "w" | "h";

export interface Market {
  id: string;
  name: string;
  region: string;
  currency: string;
}

export interface UniverseItem {
  symbol: string;
  name: string;
  market: string;
  currency: string;
  sector: string;
  base_risk: number;
  liquidity: number;
}

export interface KlineRow {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KlineResponse {
  market: string;
  symbol: string;
  period: Period;
  count: number;
  source: "live" | "mock";
  items: KlineRow[];
}

export interface RecommendReason {
  type: string;
  label: string;
  title: string;
  detail: string;
  weight: number;
}

export interface ScreenItem {
  symbol: string;
  name: string;
  market: string;
  market_name: string;
  asset_type: string;
  sector: string;
  currency: string;
  price: number;
  change_1d: number;
  change_20d: number;
  rsi14: number | null;
  trend_score: number;
  momentum_score: number;
  volatility20: number | null;
  macro_score: number;
  total_score: number;
  signals: string[];
  reasons: RecommendReason[];
}

export interface ScreenResult {
  items: ScreenItem[];
  count: number;
  total_universe: number;
  updated_at?: string;
}

export interface AnalysisData {
  price: number;
  change_1d: number;
  change_5d: number;
  change_20d: number;
  change_60d: number;
  sma5: number | null;
  sma10: number | null;
  sma20: number | null;
  sma60: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  rsi14: number | null;
  boll: { upper: number | null; middle: number | null; lower: number | null; bandwidth: number | null };
  atr14: number | null;
  atr_pct: number;
  volatility20: number | null;
  trend_score: number;
  momentum_score: number;
  volatility_score: number;
  risk_score: number;
  macro_score: number;
  total_score: number;
  signals: string[];
}

export interface MacroSnapshot {
  key: string;
  name: string;
  value: string;
  change: string;
  direction: "up" | "down";
  kind: string;
}

export interface MacroNews {
  time: string;
  title: string;
  source: string;
  tags: string[];
  sentiment: number;
}

export interface MacroBias {
  score: number;
  label: string;
  direction: "up" | "down" | "neutral";
}

export interface MacroPayload {
  snapshot: MacroSnapshot[];
  news: MacroNews[];
  bias: Record<string, MacroBias>;
  mode: "live" | "cache";
  universe_size: number;
}

export interface AnalyzeResponse {
  meta: UniverseItem;
  macro_bias: MacroBias | null;
  analysis: AnalysisData;
  kline_count: number;
}
