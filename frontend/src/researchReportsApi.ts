export interface ReportTimeframe { timeframe: string; trend: string; momentum: string; support: number | null; resistance: number | null; regime: string; latest_candle_timestamp: string; }
export interface SMCStructure { bos: string | null; fvg: string[]; order_blocks: string[]; liquidity: string[]; }
export interface FundamentalContext { news_count: number; macro_count: number; event_count: number; headlines: string[]; }
export interface MarketStatus { current_price: number; change_24h_percent: number | null; volume: number | null; volatility_percent: number | null; technical_structure: string; trend: string; momentum: string; support: number | null; resistance: number | null; market_regime: string; }
export interface ResearchReport { symbol: string; generated_at: string; market_status: MarketStatus; smc_structure: SMCStructure; multi_timeframe: ReportTimeframe[]; fundamental_context: FundamentalContext; ai_interpretation: string; bull_case: string[]; bear_case: string[]; key_risks: string[]; invalidation: string[]; overall_research_score: number; score_basis: Record<string, number>; }

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function getResearchReport(symbol: string): Promise<ResearchReport> {
  const response = await fetch(`${API_BASE}/api/research-reports/${encodeURIComponent(symbol)}`, { credentials: "include" });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try { const body = await response.json() as { detail?: string }; if (body.detail) message = body.detail; } catch {}
    throw new Error(message);
  }
  return await response.json() as ResearchReport;
}
