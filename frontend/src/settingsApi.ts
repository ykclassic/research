import { ApiError } from "./api";

export interface AccountInfo {
  id: string;
  email: string;
  created_at: string | null;
  email_confirmed_at: string | null;
  last_sign_in_at: string | null;
  account_status: "active" | "email_unconfirmed";
}

export interface ResearchPreferences {
  default_asset: string;
  default_asset_class: "Crypto" | "Forex" | "Stocks";
  default_timeframe: "15m" | "1h" | "4h" | "1D";
  analysis_depth: "Quick" | "Standard" | "Comprehensive";
  technical_analysis_enabled: boolean;
  market_structure_enabled: boolean;
  multi_timeframe_enabled: boolean;
  fundamental_analysis_enabled: boolean;
  news_analysis_enabled: boolean;
  ai_interpretation_enabled: boolean;
}

export interface SignalPreferences {
  minimum_confidence: number;
  preferred_signal_types: Array<"BUY" | "SELL" | "NEUTRAL">;
  minimum_risk_reward: number;
  require_multi_timeframe_confirmation: boolean;
  require_market_structure_confirmation: boolean;
}

export interface AlertPreferences {
  browser_notifications_enabled: boolean;
  email_alerts_enabled: boolean;
  high_confidence_signal_alerts: boolean;
  price_alerts: boolean;
  regime_change_alerts: boolean;
  news_event_alerts: boolean;
  report_completion_alerts: boolean;
  frequency: "Immediate" | "Batched" | "Daily digest" | "Off";
}

export interface MarketDataPreferences {
  maximum_data_age_seconds: number;
  reject_stale_data: boolean;
  require_completed_candles: boolean;
  allow_cached_data_fallback: boolean;
}

export interface DisplayPreferences {
  theme: "light" | "dark" | "system";
  density: "compact" | "comfortable";
  sidebar_collapsed: boolean;
  default_landing_page: string;
  currency: "USD";
  timezone: string;
  market_timestamps: "utc" | "local" | "exchange";
  date_format: "DD/MM/YYYY" | "MM/DD/YYYY" | "YYYY-MM-DD";
  time_format: "12-hour" | "24-hour";
  reduce_animations: boolean;
}

export interface AIOutputSections {
  executive_summary: boolean;
  technical_outlook: boolean;
  fundamental_outlook: boolean;
  news_impact: boolean;
  market_regime: boolean;
  bull_scenario: boolean;
  base_scenario: boolean;
  bear_scenario: boolean;
  key_risks: boolean;
  catalysts: boolean;
  invalidations: boolean;
}

export interface AIPreferences {
  enabled: boolean;
  analysis_style: "Concise" | "Analytical" | "Detailed";
  interpretation_risk: "Conservative" | "Balanced" | "Aggressive";
  require_evidence: boolean;
  show_confidence_scores: boolean;
  show_supporting_indicators: boolean;
  show_conflicting_evidence: boolean;
  output_sections: AIOutputSections;
}

export interface PrivacyPreferences {
  research_history_retention_days: number;
  save_generated_reports: boolean;
  save_ai_research: boolean;
  save_search_history: boolean;
  analytics_telemetry_enabled: boolean;
}

export interface UserPreferences {
  id: string;
  user_id: string;
  research_preferences: ResearchPreferences;
  signal_preferences: SignalPreferences;
  alert_preferences: AlertPreferences;
  market_data_preferences: MarketDataPreferences;
  display_preferences: DisplayPreferences;
  ai_preferences: AIPreferences;
  privacy_preferences: PrivacyPreferences;
  created_at: string;
  updated_at: string;
}

export type PreferencesDraft = Omit<UserPreferences, "id" | "user_id" | "created_at" | "updated_at">;

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const CSRF_STORAGE_KEY = "mr_csrf_token";
const REQUEST_TIMEOUT_MS = 12_000;

function getCookie(name: string): string | null {
  const encodedName = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie.split(";").map(item => item.trim()).find(item => item.startsWith(encodedName));
  return cookie ? decodeURIComponent(cookie.slice(encodedName.length)) : null;
}

function getStoredCsrf(): string | null {
  try { return window.sessionStorage.getItem(CSRF_STORAGE_KEY); } catch { return null; }
}

function storeCsrf(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(CSRF_STORAGE_KEY, token);
    else window.sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } catch { /* storage may be unavailable */ }
}

async function requestCsrfToken(): Promise<string> {
  const response = await fetch(`${API_BASE}/api/auth/csrf`, { method: "GET", credentials: "include" });
  if (!response.ok) throw new ApiError("Unable to initialize secure settings actions.", response.status);
  const token = response.headers.get("X-CSRF-Token");
  if (!token) throw new ApiError("The API did not return a CSRF token.", 503);
  storeCsrf(token);
  return token;
}

async function request<T>(path: string, init: RequestInit = {}, mutation = false): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (mutation) {
    const csrf = getStoredCsrf() ?? getCookie("mr_csrf") ?? await requestCsrfToken();
    headers.set("X-CSRF-Token", csrf);
  }

  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include", signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The application server did not respond in time.", 0);
    }
    throw new ApiError("Unable to reach the application server.", 0);
  } finally {
    globalThis.clearTimeout(timeout);
  }

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = await response.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch { /* ignore non-JSON errors */ }
    if (mutation && response.status === 403 && message === "CSRF validation failed.") {
      storeCsrf(null);
      const csrf = await requestCsrfToken();
      return request<T>(path, { ...init, headers: { ...Object.fromEntries(headers.entries()), "X-CSRF-Token": csrf } }, false);
    }
    throw new ApiError(message, response.status);
  }

  const responseCsrf = response.headers.get("X-CSRF-Token");
  if (responseCsrf) storeCsrf(responseCsrf);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function getAccountInfo(): Promise<AccountInfo> {
  return request<AccountInfo>("/api/auth/me");
}

export async function getPreferences(): Promise<UserPreferences> {
  return request<UserPreferences>("/api/preferences");
}

export async function savePreferences(preferences: PreferencesDraft): Promise<UserPreferences> {
  return request<UserPreferences>("/api/preferences", { method: "PUT", body: JSON.stringify(preferences) }, true);
}

export async function resetPreferences(): Promise<UserPreferences> {
  return request<UserPreferences>("/api/preferences/reset", { method: "POST" }, true);
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<string> {
  return (await request<{ message: string }>("/api/auth/password/change", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  }, true)).message;
}

export async function requestAccountPasswordReset(email: string): Promise<string> {
  return (await request<{ message: string }>("/api/auth/password-reset/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  })).message;
}

export async function signOutOtherSessions(): Promise<string> {
  return (await request<{ message: string }>("/api/auth/sessions/sign-out-others", { method: "POST" }, true)).message;
}

export async function signOutAllSessions(): Promise<void> {
  await request<void>("/api/auth/sessions/sign-out-all", { method: "POST" }, true);
  storeCsrf(null);
}

export async function deleteResearchHistory(): Promise<string> {
  return (await request<{ message: string }>("/api/preferences/data/research-history", { method: "DELETE" }, true)).message;
}

export async function deleteAllWatchlists(): Promise<string> {
  return (await request<{ message: string }>("/api/preferences/data/watchlists", { method: "DELETE" }, true)).message;
}

export async function deleteAccount(): Promise<void> {
  await request<void>("/api/auth/account", { method: "DELETE", body: JSON.stringify({ confirmation: "DELETE" }) }, true);
  storeCsrf(null);
}
