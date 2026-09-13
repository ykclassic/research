export interface ReportTimeframe { timeframe: string; trend: string; momentum: string; support: number | null; resistance: number | null; regime: string; latest_candle_timestamp: string; }
export interface SMCStructure { bos: string | null; fvg: string[]; order_blocks: string[]; liquidity: string[]; }
export interface FundamentalContext { news_count: number; macro_count: number; event_count: number; headlines: string[]; }
export interface MarketStatus { current_price: number; change_24h_percent: number | null; volume: number | null; volatility_percent: number | null; technical_structure: string; trend: string; momentum: string; support: number | null; resistance: number | null; market_regime: string; }
export interface ResearchRequestConfiguration {
  default_asset: string;
  default_asset_class: string;
  default_timeframe: string;
  analysis_depth: string;
  technical_analysis: boolean;
  market_structure: boolean;
  multi_timeframe: boolean;
  fundamental_analysis: boolean;
  news_analysis: boolean;
  ai_interpretation: boolean;
}
export interface ResearchReport {
  symbol: string;
  generated_at: string;
  request_configuration: ResearchRequestConfiguration | null;
  market_status: MarketStatus;
  indicators: Record<string, number | string | null>;
  regime_snapshot: Record<string, unknown>;
  smc_structure: SMCStructure;
  multi_timeframe: ReportTimeframe[];
  fundamental_context: FundamentalContext;
  ai_interpretation: string | null;
  bull_case: string[];
  bear_case: string[];
  key_risks: string[];
  invalidation: string[];
  overall_research_score: number;
  score_basis: Record<string, number>;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function getResearchReport(symbol?: string): Promise<ResearchReport> {
  const path = symbol
    ? `/api/research-reports/${encodeURIComponent(symbol)}`
    : "/api/research-reports";
  const response = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try { const body = await response.json() as { detail?: string }; if (body.detail) message = body.detail; } catch {}
    throw new Error(message);
  }
  return await response.json() as ResearchReport;
}
