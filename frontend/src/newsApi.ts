export type EventType = "NEWS" | "EARNINGS" | "ECONOMIC" | "MACRO" | "REGULATORY" | "CORPORATE" | "OTHER";
export type SentimentLabel = "POSITIVE" | "NEGATIVE" | "NEUTRAL";

export interface NewsItem {
  id: string;
  headline: string;
  summary: string;
  source: string;
  source_url: string | null;
  published_at: string;
  related_entities: string[];
  affected_assets: string[];
  event_type: EventType;
  sentiment: SentimentLabel;
  sentiment_score: number;
  provider: string;
}

export interface FundamentalEvent {
  id: string;
  event_type: EventType;
  title: string;
  description: string;
  source: string;
  source_url: string | null;
  event_timestamp: string;
  affected_assets: string[];
  country: string | null;
  importance: string | null;
  actual: number | string | null;
  estimate: number | string | null;
  previous: number | string | null;
  surprise: number | string | null;
  provider: string;
}

export interface MarketReaction {
  baseline_timestamp: string | null;
  reaction_timestamp: string | null;
  baseline_price: number | null;
  reaction_price: number | null;
  absolute_change: number | null;
  percent_change: number | null;
  direction: string;
  timeframe: string;
}

export interface TechnicalRegimeContext {
  regime: string;
  confidence: number;
  trend_direction: string;
  latest_candle_timestamp: string;
  timeframe: string;
}

export interface NewsCorrelation {
  news_id: string;
  news_headline: string;
  event_type: EventType;
  affected_asset: string;
  published_at: string;
  sentiment: SentimentLabel;
  market_reaction: MarketReaction;
  technical_regime: TechnicalRegimeContext | null;
}

export interface NewsResearchResponse {
  symbol: string | null;
  generated_at: string;
  provider: string;
  news: NewsItem[];
  fundamental_events: FundamentalEvent[];
  correlations: NewsCorrelation[];
  coverage: Record<string, number>;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function getNewsResearch(symbol: string | null, days = 1, limit = 25): Promise<NewsResearchResponse> {
  const params = new URLSearchParams({ days: String(days), limit: String(limit) });
  if (symbol) params.set("symbol", symbol);
  const response = await fetch(`${API_BASE}/api/news/research?${params}`, { credentials: "include" });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {}
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return await response.json() as NewsResearchResponse;
}
