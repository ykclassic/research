export type QuoteStatus = "LIVE" | "DELAYED" | "STALE" | "UNAVAILABLE" | "MARKET_CLOSED";
export type FreshnessStatus = "FRESH" | "DELAYED" | "STALE" | "UNKNOWN";
export type CompletenessStatus = "COMPLETE" | "PARTIAL" | "INVALID" | "UNKNOWN" | "NOT_APPLICABLE";
export type ProviderErrorCode = "RATE_LIMITED" | "QUOTA_EXHAUSTED" | "AUTHENTICATION_FAILURE" | "SYMBOL_UNSUPPORTED" | "PROVIDER_TIMEOUT" | "PROVIDER_UNAVAILABLE" | "ALL_PROVIDERS_UNAVAILABLE";
export interface Quote { symbol: string; provider_symbol: string; price: number | null; currency: string | null; timestamp: string | null; provider_timestamp?: string | null; observed_at?: string | null; source: string | null; status: QuoteStatus; market_open: boolean | null; latency_ms: number | null; cache_hit?: boolean; error: string | null; error_code?: ProviderErrorCode | null; freshness_status?: FreshnessStatus; freshness_age_seconds?: number | null; completeness_status?: CompletenessStatus; fallback_used?: boolean; provider_attempts?: string[]; provider_credits_used?: number | null; provider_credits_remaining?: number | null; }
export interface ProviderStatus { provider: string; configured: boolean; reachable: boolean | null; circuit_open: boolean; consecutive_failures: number; last_latency_ms: number | null; last_error: string | null; last_error_code: ProviderErrorCode | null; credits_used: number | null; credits_remaining: number | null; usage_observed_at: string | null; quote_budget_remaining: number | null; daily_quote_budget_remaining: number | null; message: string; }
export interface MarketStatus { providers: ProviderStatus[]; quote_cache_entries: number; candle_cache_entries: number; }
export type MarketSessionAssetClass = "crypto" | "forex" | "stocks";
export type MarketSessionVolatilityState = "VERY_HIGH" | "HIGH" | "MODERATE" | "LOW" | "VERY_LOW" | "UNKNOWN";
export interface MarketSessionState {
  asset_class: MarketSessionAssetClass;
  label: string;
  phase: string;
  status: "OPEN" | "CLOSED";
  market_open: boolean;
  volatility_score: number | null;
  volatility_state: MarketSessionVolatilityState;
  activity_score: number | null;
  liquidity_state: "VERY_HIGH" | "HIGH" | "MODERATE" | "UNKNOWN";
  starts_at: string | null;
  ends_at: string | null;
  next_transition_at: string | null;
  volatility_source: string | null;
  timestamp: string;
}
export interface MarketSession {
  calculated_at: string;
  sessions: MarketSessionState[];
  representative_symbols: Record<MarketSessionAssetClass, string>;
}
export interface User { id: string; email: string; created_at: string; }
export interface WatchlistItem { id: string; symbol: string; created_at: string; }
export interface Watchlist { id: string; user_id: string; name: string; created_at: string; updated_at: string; watchlist_items: WatchlistItem[]; }
export interface Candle { timestamp: string; open: number; high: number; low: number; close: number; volume: number | null; is_complete: boolean; }
export interface IndicatorPoint { timestamp: string; value: number | null; }
export interface IndicatorPane { id: string; title: string; unit: string; min: number | null; max: number | null; points: IndicatorPoint[]; }
export interface AnalysisQuality { request_latency_ms: number | null; freshness_status: FreshnessStatus; freshness_age_seconds: number | null; candle_completeness: CompletenessStatus; provenance_provider: string; provider_attempts: string[]; fallback_used: boolean; cache_hit: boolean; research_eligible: boolean; }
export interface TechnicalAnalysis { symbol: string; timeframe: string; source: string; calculated_at: string; latest_candle_timestamp: string; candle_count: number; candles: Candle[]; current_quote: Quote; indicators: Record<string, number | string | null>; indicator_panes: IndicatorPane[]; data_quality?: AnalysisQuality; }
export type MarketRegime = "STRONG_TREND_UP" | "STRONG_TREND_DOWN" | "WEAK_TREND" | "RANGE" | "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "UNKNOWN";
export interface RegimeEvidence { price: number; ema_50: number | null; ema_200: number | null; price_above_ema_200: boolean | null; ema_50_above_ema_200: boolean | null; adx: number | null; atr: number | null; atr_percent: number | null; atr_percentile: number | null; bb_width: number | null; bb_width_percentile: number | null; trend_direction: string; trend_persistence: number; directional_move_ratio: number; }
export interface RegimeThresholds { adx_strong: number; persistence_strong: number; persistence_weak: number; directional_ratio_strong: number; directional_ratio_weak: number; volatility_high_percentile: number; volatility_low_percentile: number; }
export interface RegimeResult { symbol: string; timeframe: string; source: string; calculated_at: string; provider_timestamp: string | null; latest_candle_timestamp: string; candle_count: number; regime: MarketRegime; confidence: number; evidence: RegimeEvidence; thresholds: RegimeThresholds; rule_id: string; rule: string; request_latency_ms?: number | null; freshness_status?: FreshnessStatus; freshness_age_seconds?: number | null; completeness_status?: CompletenessStatus; fallback_used?: boolean; provider_attempts?: string[]; cache_hit?: boolean; }
export type TechnicalAnalysisRange = { startDate?: string; endDate?: string };
export type StructureStatus = "ACTIVE" | "BROKEN" | "CONFIRMED" | "INVALIDATED";
export interface StructureEvent { type: string; price: number; time: string; timeframe: string; strength: number; status: StructureStatus; invalidation: number | null; source_candles: string[]; }

export async function phase10Mutation<T>(path: string, init: RequestInit): Promise<T> { return request<T>(path, init); }
