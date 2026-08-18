import type {
  AnalyzeResponse,
  KlineResponse,
  MacroPayload,
  Period,
  ScreenResult,
} from "./types";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`请求失败 ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchScreen(params: {
  market: string;
  minScore: number;
  minTrend: number;
  minRsi: number;
  maxRsi: number;
  sortBy: string;
  limit?: number;
}): Promise<ScreenResult> {
  const query = new URLSearchParams({
    market: params.market,
    min_score: String(params.minScore),
    min_trend: String(params.minTrend),
    min_rsi: String(params.minRsi),
    max_rsi: String(params.maxRsi),
    sort_by: params.sortBy,
    limit: String(params.limit ?? 80),
  });
  return getJson<ScreenResult>(`/api/screen?${query.toString()}`);
}

export function fetchRecommendations(limit = 10): Promise<ScreenResult> {
  const query = new URLSearchParams({ limit: String(limit) });
  return getJson<ScreenResult>(`/api/recommendations?${query.toString()}`);
}

export function fetchKline(
  market: string,
  symbol: string,
  period: Period,
  limit = 220,
  real = true,
): Promise<KlineResponse> {
  const query = new URLSearchParams({ market, symbol, period, limit: String(limit), real: String(real) });
  return getJson<KlineResponse>(`/api/kline?${query.toString()}`);
}

export function fetchAnalysis(market: string, symbol: string): Promise<AnalyzeResponse> {
  const query = new URLSearchParams({ market, symbol });
  return getJson<AnalyzeResponse>(`/api/analyze?${query.toString()}`);
}

export function fetchMacro(): Promise<MacroPayload> {
  return getJson<MacroPayload>("/api/macro");
}
