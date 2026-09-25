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
export interface MarketStructureResult { symbol: string; timeframe: string; source: string; calculated_at: string; latest_candle_timestamp: string; candle_count: number; events: StructureEvent[]; }
export type MTFBias = "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
export type MTFState = "DAILY_BIAS" | "H4_TREND" | "H1_PULLBACK" | "H1_CONTINUATION" | "H1_REVERSAL" | "H1_NEUTRAL" | "M15_BULLISH_BOS" | "M15_BEARISH_BOS" | "M15_CONFIRMATION" | "M15_NEUTRAL" | "UNKNOWN";
export interface MTFTimeframeAnalysis { timeframe: string; bias: MTFBias; state: MTFState; conclusion: string; confidence: number; latest_candle_timestamp: string; source: string; candle_count: number; evidence: string[]; }
export interface MTFResearchConclusion { alignment_count: number; alignment_total: 4; bias: MTFBias; confidence: number; primary_setup: string; invalidation: string; conclusion: string; }
export interface MultiTimeframeResult { symbol: string; calculated_at: string; timeframes: MTFTimeframeAnalysis[]; research: MTFResearchConclusion; }
export type SignalDirection = "NEUTRAL" | "BUY" | "STRONG_BUY" | "SELL" | "STRONG_SELL";
export type SignalQualificationStatus = "QUALIFIED" | "REJECTED";
export type RiskRewardStatus = "AVAILABLE" | "UNAVAILABLE";
export interface SignalComponent { timeframe: string; indicator_score: number; smc_score: number; combined_score: number; evidence: string[]; }
export interface CryptoSignal { signal_id: string; symbol: string; signal: SignalDirection; score: number; confidence: number; confluence: number; risk_reward: number | null; risk_reward_status: RiskRewardStatus; risk_reward_reason: string | null; structural_target: number | null; atr_minimum_target: number | null; price: number; entry_price: number; stop_loss: number | null; take_profit: number | null; atr: number | null; calculated_at: string; latest_candle_timestamp: string; source: string; components: SignalComponent[]; evidence: string[]; research_eligible: boolean; qualification_reasons: string[]; minimum_confidence: number; minimum_risk_reward: number; qualification_status: SignalQualificationStatus; }
export interface CryptoSignalList { calculated_at: string; signals: CryptoSignal[]; }
export type SignalOutcomeStatus = "PENDING" | "TARGET_HIT" | "STOP_LOSS_HIT" | "AMBIGUOUS";
export interface SignalOutcomeRecord {
  record_id: string;
  signal_id: string;
  revision: number;
  symbol: string;
  signal: SignalDirection;
  score: number;
  confidence: number;
  dispatched_at: string;
  entry_price: number;
  stop_loss: number | null;
  target_price: number | null;
  target_tagged_at: string | null;
  stop_tagged_at: string | null;
  target_tag_latency_seconds: number | null;
  stop_tag_latency_seconds: number | null;
  first_touch_price: number | null;
  first_touch_timestamp: string | null;
  outcome: SignalOutcomeStatus;
  provider: string;
  timeframe: string;
  signal_engine_version: string;
  calculated_at: string;
  latest_candle_timestamp: string;
  observed_at: string;
  observation_candle_timestamp: string | null;
  observation_source: string | null;
  coverage_warning: string | null;
}
export interface AIResearchResponse { symbol: string; timeframe: string; deterministic_gate: "PASSED"; verified_context: Record<string, unknown>; report: string; model: string; }
export type PositionSide = "LONG" | "SHORT";
export interface PortfolioPosition { id: string; user_id: string; symbol: string; side: PositionSide; quantity: number; average_entry_price: number; asset_class: string; sector: string; category: string; notes: string | null; created_at: string; updated_at: string; }
export interface PortfolioPositionSnapshot { position: PortfolioPosition; current_price: number | null; market_value: number; unrealized_pnl: number | null; pnl_percent: number | null; quote_status: string; quote_timestamp: string | null; }
export interface PortfolioSummary { calculated_at: string; position_count: number; invested_value: number; gross_exposure: number; net_exposure: number; unrealized_pnl: number; unrealized_pnl_percent: number | null; max_position_concentration_percent: number; portfolio_drawdown_percent: number; risk_flags: string[]; positions: PortfolioPositionSnapshot[]; }
export interface PortfolioScenario { price_change_percent: number; projected_unrealized_pnl: number; projected_pnl_delta: number; projected_gross_exposure: number; affected_positions: number; }
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function formatApiErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (typeof detail === "number" || typeof detail === "boolean") return String(detail);
  if (Array.isArray(detail)) {
    const items = detail.map(item => formatApiErrorDetail(item)).filter((item): item is string => Boolean(item));
    return items.length ? items.join(" ") : null;
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    const preferredKeys = ["message", "detail", "reasons", "error", "errors"];
    const preferred = preferredKeys
      .map(key => formatApiErrorDetail(record[key]))
      .filter((item): item is string => Boolean(item));
    if (preferred.length) return [...new Set(preferred)].join(" ");

    const entries = Object.entries(record)
      .map(([key, value]) => {
        const formatted = formatApiErrorDetail(value);
        return formatted ? key + ": " + formatted : null;
      })
      .filter((item): item is string => Boolean(item));
    if (entries.length) return entries.join(" ");

    try {
      const serialized = JSON.stringify(detail);
      return serialized && serialized !== "{}" ? serialized : null;
    } catch {
      return null;
    }
  }
  return null;
}

async function readApiError(response: Response): Promise<{ message: string; detail: unknown }> {
  try {
    const body = await response.json() as { detail?: unknown; message?: unknown };
    const detail = body?.detail ?? body?.message ?? null;
    return {
      message: formatApiErrorDetail(detail) ?? ("Request failed: " + response.status),
      detail,
    };
  } catch {
    return { message: "Request failed: " + response.status, detail: null };
  }
}
const PRODUCTION_API_BASE = "https://research-76vr.onrender.com";
const configuredApiBase = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
const hostname = typeof window !== "undefined" ? window.location.hostname : "";
const isLocalHost = hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
const configuredApiIsLocal = /^(https?:\/\/)?(localhost|127\.0\.0\.1)(:\d+)?\/?$/i.test(configuredApiBase);
const API_BASE = (configuredApiBase && (!isLocalHost && !configuredApiIsLocal) ? configuredApiBase : isLocalHost ? (configuredApiBase || "http://localhost:8000") : PRODUCTION_API_BASE).replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 60_000;
const SIGNAL_REQUEST_TIMEOUT_MS = 20_000;
const AI_REQUEST_TIMEOUT_MS = 60_000;
const CSRF_STORAGE_KEY = "mr_csrf_token";
function getCookie(name: string): string | null { const encodedName = `${encodeURIComponent(name)}=`; const cookie = document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith(encodedName)); return cookie ? decodeURIComponent(cookie.slice(encodedName.length)) : null; }
function getStoredCsrf(): string | null { try { return window.sessionStorage.getItem(CSRF_STORAGE_KEY); } catch { return null; } }
function storeCsrf(token: string | null): void { try { if (token) window.sessionStorage.setItem(CSRF_STORAGE_KEY, token); else window.sessionStorage.removeItem(CSRF_STORAGE_KEY); } catch {} }
async function requestCsrfToken(): Promise<string> { const response = await fetch(`${API_BASE}/api/auth/csrf`, { method: "GET", credentials: "include" }); if (!response.ok) { const error = await readApiError(response); throw new ApiError(error.message, response.status, error.detail); } const token = response.headers.get("X-CSRF-Token"); if (!token) throw new ApiError("The API did not return a CSRF token.", 503); storeCsrf(token); return token; }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> { const headers = new Headers(init.headers); if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json"); if (init.method && init.method !== "GET") { const csrf = getStoredCsrf() ?? getCookie("mr_csrf"); if (csrf) headers.set("X-CSRF-Token", csrf); } const controller = new AbortController(); const timeoutMs = path.startsWith("/api/ai-research/") ? AI_REQUEST_TIMEOUT_MS : path.startsWith("/api/signals/") ? SIGNAL_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS; let timeoutId: ReturnType<typeof setTimeout> | undefined; let removeAbortListener: (() => void) | undefined; if (init.signal) { if (init.signal.aborted) controller.abort(init.signal.reason); else { const abort = () => controller.abort(init.signal?.reason); init.signal.addEventListener("abort", abort, { once: true }); removeAbortListener = () => init.signal?.removeEventListener("abort", abort); } } timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs); let response: Response; try { response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include", signal: controller.signal }); } catch (error) { if (error instanceof DOMException && error.name === "AbortError") throw new ApiError(`The application server did not respond within ${timeoutMs / 1000} seconds. Check the API deployment and try again.`, 0); throw new ApiError("Unable to reach the application server. Check your connection and try again.", 0); } finally { if (timeoutId !== undefined) globalThis.clearTimeout(timeoutId); removeAbortListener?.(); } if (!response.ok) { const error = await readApiError(response); throw new ApiError(error.message, response.status, error.detail); } const responseCsrf = response.headers.get("X-CSRF-Token"); if (responseCsrf) storeCsrf(responseCsrf); if (response.status === 204) return undefined as T; return await response.json() as T; }
async function authenticatedMutation<T>(path: string, init: RequestInit): Promise<T> { if (!getStoredCsrf() && !getCookie("mr_csrf")) await requestCsrfToken(); try { return await request<T>(path, init); } catch (error) { if (error instanceof ApiError && error.status === 403 && error.message === "CSRF validation failed.") { storeCsrf(null); await requestCsrfToken(); return request<T>(path, init); } throw error; } }
export async function register(email: string, password: string): Promise<User> { return request<User>("/api/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }); }
export async function login(email: string, password: string): Promise<User> { storeCsrf(null); const user = await request<User>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); await requestCsrfToken(); return user; }
export async function requestPasswordReset(email: string): Promise<string> { return (await request<{ message: string }>("/api/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email }) })).message; }
export async function confirmPasswordReset(accessToken: string, password: string): Promise<string> { return (await request<{ message: string }>("/api/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ access_token: accessToken, password }) })).message; }
export async function getCurrentUser(): Promise<User> { return request<User>("/api/auth/me"); }
export async function logout(): Promise<void> { await authenticatedMutation<void>("/api/auth/logout", { method: "POST" }); storeCsrf(null); }
export async function getQuotes(symbols: string[], refresh = false): Promise<Quote[]> { const params = new URLSearchParams({ symbols: symbols.join(","), refresh: String(refresh) }); return (await request<{ quotes: Quote[] }>(`/api/market/quotes?${params}`)).quotes; }
export async function getMarketStatus(): Promise<MarketStatus> { return request<MarketStatus>("/api/market/status"); }
export async function getMarketSession(): Promise<MarketSession> { return request<MarketSession>("/api/market/session"); }
export async function getWatchlists(): Promise<Watchlist[]> { return (await request<{ watchlists: Watchlist[] }>("/api/watchlists")).watchlists; }
export async function createWatchlist(name: string): Promise<Watchlist> { return authenticatedMutation<Watchlist>("/api/watchlists", { method: "POST", body: JSON.stringify({ name }) }); }
export async function renameWatchlist(id: string, name: string): Promise<Watchlist> { return authenticatedMutation<Watchlist>(`/api/watchlists/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify({ name }) }); }
export async function deleteWatchlist(id: string): Promise<void> { await authenticatedMutation<void>(`/api/watchlists/${encodeURIComponent(id)}`, { method: "DELETE" }); }
export async function addWatchlistSymbol(id: string, symbol: string): Promise<WatchlistItem> { return authenticatedMutation<WatchlistItem>(`/api/watchlists/${encodeURIComponent(id)}/symbols`, { method: "POST", body: JSON.stringify({ symbol }) }); }
export async function removeWatchlistSymbol(id: string, symbol: string): Promise<void> { await authenticatedMutation<void>(`/api/watchlists/${encodeURIComponent(id)}/symbols/${encodeURIComponent(symbol)}`, { method: "DELETE" }); }
export async function getTechnicalAnalysis(symbol: string, timeframe = "1h", limit = 250, range: TechnicalAnalysisRange = {}): Promise<TechnicalAnalysis> { const params = new URLSearchParams({ timeframe }); if (range.startDate || range.endDate) { if (!range.startDate || !range.endDate) throw new Error("A historical range requires both a start date and an end date."); params.set("start", range.startDate); params.set("end", range.endDate); } else params.set("limit", String(limit)); return request<TechnicalAnalysis>(`/api/analysis/${encodeURIComponent(symbol)}?${params}`); }
export async function getMarketRegime(symbol: string, timeframe = "1h", limit = 250): Promise<RegimeResult> { const params = new URLSearchParams({ timeframe, limit: String(limit) }); return request<RegimeResult>(`/api/regime/${encodeURIComponent(symbol)}?${params}`); }
export async function getMarketStructure(symbol: string, timeframe = "1h", limit = 250): Promise<MarketStructureResult> { const params = new URLSearchParams({ timeframe, limit: String(limit) }); return request<MarketStructureResult>(`/api/market-structure/${encodeURIComponent(symbol)}?${params}`); }
export async function getMultiTimeframeAnalysis(symbol: string, limit = 250): Promise<MultiTimeframeResult> { const params = new URLSearchParams({ limit: String(limit) }); return request<MultiTimeframeResult>(`/api/mtf/${encodeURIComponent(symbol)}?${params}`); }
export async function getCryptoSignals(limit = 250): Promise<CryptoSignalList> { const params = new URLSearchParams({ limit: String(limit) }); return request<CryptoSignalList>(`/api/signals?${params}`); }
export async function getSignal(symbol: string, limit = 250): Promise<CryptoSignal> { const params = new URLSearchParams({ limit: String(limit) }); return request<CryptoSignal>(`/api/signals/${encodeURIComponent(symbol)}?${params}`); }
export async function createAIResearchReport(symbol: string, timeframe = "1h", limit = 250, question?: string): Promise<AIResearchResponse> { return authenticatedMutation<AIResearchResponse>("/api/ai-research/report", { method: "POST", body: JSON.stringify({ symbol, timeframe, limit, question }) }); }
export async function getPortfolioSummary(): Promise<PortfolioSummary> { return request<PortfolioSummary>("/api/portfolio/summary"); }
export async function createPortfolioPosition(payload: { symbol: string; side: PositionSide; quantity: number; average_entry_price: number; asset_class?: string; sector?: string; category?: string; notes?: string }): Promise<PortfolioPosition> { return authenticatedMutation<PortfolioPosition>("/api/portfolio/positions", { method: "POST", body: JSON.stringify(payload) }); }
export async function deletePortfolioPosition(id: string): Promise<void> { await authenticatedMutation<void>(`/api/portfolio/positions/${encodeURIComponent(id)}`, { method: "DELETE" }); }
export async function runPortfolioScenario(priceChangePercent: number): Promise<PortfolioScenario> { return request<PortfolioScenario>("/api/portfolio/scenario", { method: "POST", body: JSON.stringify({ price_change_percent: priceChangePercent }) }); }

export interface SignalIntelligenceSnapshot {
  id: string; signal_id: string; revision: number; symbol: string; direction: string;
  confidence: number; entry_price: number; stop_loss: number; target_price: number;
  risk_reward: number | null; timeframe: string; mtf_bias: string | null; mtf_alignment: number | null;
  regime: string | null; regime_confidence: number | null; market_structure: string | null;
  liquidity_conditions: string | null; momentum: number | null; volatility: number | null;
  session: string | null; strategy: string; outcome: string; dispatched_at: string;
  target_timestamp: string | null; stop_timestamp: string | null; first_touch_timestamp: string | null;
  r_result: number | null; outcome_latency_seconds: number | null; signal_engine_version: string;
  evidence: string[]; replay_candles: Array<{timestamp:string;open:number;high:number;low:number;close:number;volume:number;timeframe:string;source:string}>;
  structural_conditions: Record<string, unknown>;
}
export interface SignalExplorerResult { total: number; sample_size_note: string; signals: SignalIntelligenceSnapshot[]; }
export interface CalibrationBucket { label: string; lower: number; upper: number | null; sample_size: number; observed_outcome_rate: number | null; mean_r: number | null; statistically_meaningful: boolean; note: string; }
export interface SignalCalibration { minimum_sample_size: number; total_samples: number; buckets: CalibrationBucket[]; }
export interface EngineVersionMetric { engine_version: string; sample_size: number; target_hit_rate: number; mean_r: number | null; median_r: number | null; mean_latency_seconds: number | null; statistically_meaningful: boolean; note: string; }
export interface EngineVersionAnalytics { minimum_sample_size: number; versions: EngineVersionMetric[]; }
export interface SignalReplay { signal: SignalIntelligenceSnapshot; chronological_states: Array<Record<string, unknown>>; outcome: string; methodology_note: string; }
export async function getSignalIntelligence(filters: Record<string,string|number|undefined> = {}): Promise<SignalExplorerResult> { const params = new URLSearchParams(); Object.entries(filters).forEach(([k,v])=>{ if(v!==undefined&&v!=="") params.set(k,String(v)); }); return request<SignalExplorerResult>("/api/signal-intelligence/explorer?"+params.toString()); }
export async function getSignalCalibration(): Promise<SignalCalibration> { return request<SignalCalibration>("/api/signal-intelligence/calibration"); }
export async function getSignalEngineVersions(): Promise<EngineVersionAnalytics> { return request<EngineVersionAnalytics>("/api/signal-intelligence/engine-versions"); }
export async function getSignalSimilarity(signalId: string): Promise<SignalExplorerResult> { return request<SignalExplorerResult>("/api/signal-intelligence/similar/"+encodeURIComponent(signalId)); }
export async function getSignalReplay(signalId: string): Promise<SignalReplay> { return request<SignalReplay>("/api/signal-intelligence/replay/"+encodeURIComponent(signalId)); }

export async function logSignal(signal: CryptoSignal): Promise<SignalOutcomeRecord> { return authenticatedMutation<SignalOutcomeRecord>("/api/signal-outcomes/log", { method: "POST", body: JSON.stringify({ signal }) }); }
export async function getSignalOutcomes(limit = 50): Promise<SignalOutcomeRecord[]> { const params = new URLSearchParams({ limit: String(limit) }); return request<SignalOutcomeRecord[]>(`/api/signal-outcomes?${params}`); }
export async function getSignalOutcome(signalId: string, refresh = true): Promise<SignalOutcomeRecord> { const params = new URLSearchParams({ refresh: String(refresh) }); return request<SignalOutcomeRecord>(`/api/signal-outcomes/${encodeURIComponent(signalId)}?${params}`); }


export interface ScannerConditionRule { field: "confidence"|"risk_reward"|"mtf_alignment"|"momentum"|"volatility"|"volume"|"direction"|"regime"|"structure"|"liquidity"|"signal_status"|"trend"; operator: "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"contains"|"in"; value: string|number|boolean|string[]; }
export interface ScannerConditions {
  min_confidence?: number;
  min_risk_reward?: number;
  regimes: string[];
  directions: string[];
  structures: string[];
  min_mtf_alignment?: number;
  min_momentum?: number;
  max_volatility?: number;
  min_volume?: number;
  require_qualified: boolean;
  custom_match: "ALL"|"ANY";
  custom_conditions: ScannerConditionRule[];
}
export type ScannerPresetCreate = Omit<ScannerPreset, "id" | "user_id" | "created_at" | "updated_at" | "enabled"> & { enabled?: boolean };
export interface ScannerPreset {
  id: string; user_id: string; name: string; description: string;
  asset_universe: string[]; timeframes: string[]; conditions: ScannerConditions;
  alert_events: string[]; enabled: boolean; created_at: string; updated_at: string;
}
export interface ScannerOpportunity {
  id?: string; symbol: string; setup: string; regime: string | null; direction: string;
  confidence: number; risk_reward: number | null; structure: string | null;
  liquidity: string | null; structural_conditions: Record<string, unknown>; mtf_alignment: number | null; momentum: number | null;
  volatility: number | null; volume: number | null; trend: string | null; entry_price: number | null; stop_loss: number | null; target_price: number | null; last_price: number | null; signal_status: string;
  historical_evidence: Record<string, unknown>; signal_id: string; observed_at: string;
}
export interface ScannerRun {
  id: string; preset_id: string; status: string; scanned_count: number;
  qualified_count: number; started_at: string; completed_at: string | null;
  opportunities: ScannerOpportunity[];
}
export interface ScannerSchedule {
  id: string; user_id: string; preset_id: string; name: string;
  interval_minutes: number; enabled: boolean; next_run_at: string;
  last_run_at: string | null; created_at: string; updated_at: string;
}
export interface ScannerAlert {
  id: string; preset_id: string; opportunity_id: string | null; event_type: string;
  symbol: string; title: string; message: string; payload: Record<string, unknown>;
  triggered_at: string; read_at: string | null;
}
export async function getScannerPresets(): Promise<ScannerPreset[]> { return (await request<{items: ScannerPreset[]}>("/api/scanner/presets")).items; }
export async function createScannerPreset(payload: ScannerPresetCreate): Promise<ScannerPreset> { return (await authenticatedMutation<{item: ScannerPreset}>("/api/scanner/presets",{method:"POST",body:JSON.stringify(payload)})).item; }
export async function updateScannerPreset(id:string,payload:Partial<ScannerPreset>):Promise<ScannerPreset>{return (await authenticatedMutation<{item:ScannerPreset}>(`/api/scanner/presets/${encodeURIComponent(id)}`,{method:"PATCH",body:JSON.stringify(payload)})).item;}
export async function deleteScannerPreset(id:string):Promise<void>{await authenticatedMutation<void>(`/api/scanner/presets/${encodeURIComponent(id)}`,{method:"DELETE"});}
export async function runScanner(id:string):Promise<ScannerRun>{return authenticatedMutation<ScannerRun>(`/api/scanner/presets/${encodeURIComponent(id)}/scan`,{method:"POST"});}
export async function getScannerOpportunities():Promise<ScannerOpportunity[]>{return (await request<{items:ScannerOpportunity[]}>("/api/scanner/opportunities")).items;}
export async function getScannerSchedules():Promise<ScannerSchedule[]>{return (await request<{items:ScannerSchedule[]}>("/api/scanner/schedules")).items;}
export async function createScannerSchedule(payload:{preset_id:string;name:string;interval_minutes:number;enabled?:boolean}):Promise<ScannerSchedule>{return (await authenticatedMutation<{item:ScannerSchedule}>("/api/scanner/schedules",{method:"POST",body:JSON.stringify(payload)})).item;}
export async function updateScannerSchedule(id:string,payload:Partial<ScannerSchedule>):Promise<ScannerSchedule>{return (await authenticatedMutation<{item:ScannerSchedule}>(`/api/scanner/schedules/${encodeURIComponent(id)}`,{method:"PATCH",body:JSON.stringify(payload)})).item;}
export async function deleteScannerSchedule(id:string):Promise<void>{await authenticatedMutation<void>(`/api/scanner/schedules/${encodeURIComponent(id)}`,{method:"DELETE"});}
export async function getScannerAlerts():Promise<ScannerAlert[]>{return (await request<{items:ScannerAlert[]}>("/api/scanner/alerts")).items;}
export async function markScannerAlertRead(id:string):Promise<ScannerAlert>{return (await authenticatedMutation<{item:ScannerAlert}>(`/api/scanner/alerts/${encodeURIComponent(id)}/read`,{method:"POST"})).item;}


export type ResearchCopilotEvidence = {
  id: string;
  claim: string;
  asset?: string;
  type: string;
  timestamp: string;
  methodology: string;
  confidence?: number | null;
  data?: Record<string, unknown> | unknown[];
};

export type ResearchCopilotResult = {
  run_id: string;
  query: string;
  assets: string[];
  timeframe: string;
  intent: string;
  claim: string;
  report: string;
  evidence: ResearchCopilotEvidence[];
  sources: Array<Record<string, unknown>>;
  methodology: string;
  model: string;
  model_version: string;
  engine_version: string;
  timestamp: string | null;
  limitations: string[];
};

export async function runResearchCopilot(query: string, defaultSymbol = "BTC/USD"): Promise<ResearchCopilotResult> {
  return request("/api/research-copilot/run", { method: "POST", body: JSON.stringify({ query, default_symbol: defaultSymbol }) });
}

export async function getResearchCopilotHistory(): Promise<Array<Record<string, unknown>>> {
  return request("/api/research-copilot/history");
}


export interface PortfolioExposure { symbol:string; market_value:number; weight_percent:number; net_weight_percent:number; side:string; asset_class:string; sector:string; category:string; }
export interface CorrelationEntry { symbol:string; correlation:number; }
export interface CorrelationCluster { cluster_id:string; symbols:string[]; average_pairwise_correlation:number|null; }
export interface RiskContribution { symbol:string; exposure_percent:number; volatility_percent:number|null; risk_contribution_percent:number|null; }
export interface RegimeAlignment { symbol:string; timeframe:string; regime:string; confidence:number; alignment:string; }
export interface SignalExposure { symbol:string; active_signals:number; net_direction:string; average_confidence:number|null; regimes:string[]; }
export interface PortfolioIntelligence {
  calculated_at:string; exposures:PortfolioExposure[]; asset_allocation:Record<string,number>; sector_exposure:Record<string,number>; category_exposure:Record<string,number>;
  correlation_matrix:Record<string,CorrelationEntry[]>; correlation_clusters:CorrelationCluster[]; risk_contribution:RiskContribution[]; regime_alignment:RegimeAlignment[];
  signal_exposure:SignalExposure[]; changes:string[]; risk_drivers:string[]; alerts:string[]; relevant_signals:string[]; relevant_catalysts:string[]; data_quality:string[];
}
export interface PortfolioScenarioV2 {
  name:string; assumptions:string[]; projected_pnl_delta:number; projected_unrealized_pnl:number; projected_gross_exposure:number;
  impacts:Array<{symbol:string;shock_percent:number;pnl_delta:number;exposure_delta:number}>; affected_positions:number; data_quality:string[];
}
export async function getPortfolioIntelligence():Promise<PortfolioIntelligence>{return request<PortfolioIntelligence>("/api/portfolio/intelligence");}
export async function runDefinedPortfolioScenario(payload:{scenario_type:string;symbol?:string;shock_percent?:number}):Promise<PortfolioScenarioV2>{return request<PortfolioScenarioV2>("/api/portfolio/scenario/v2",{method:"POST",body:JSON.stringify(payload)});}
