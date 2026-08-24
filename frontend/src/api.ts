export type QuoteStatus =
  | "LIVE"
  | "DELAYED"
  | "STALE"
  | "UNAVAILABLE"
  | "MARKET_CLOSED";

export interface Quote {
  symbol: string;
  provider_symbol: string;
  price: number | null;
  currency: string | null;
  timestamp: string | null;
  source: string | null;
  status: QuoteStatus;
  market_open: boolean | null;
  latency_ms: number | null;
  error: string | null;
}

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface WatchlistItem {
  id: string;
  symbol: string;
  created_at: string;
}

export interface Watchlist {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
  updated_at: string;
  watchlist_items: WatchlistItem[];
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 12_000;

function getCookie(name: string): string | null {
  const encodedName = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(encodedName));
  return cookie ? decodeURIComponent(cookie.slice(encodedName.length)) : null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (init.method && init.method !== "GET") {
    const csrf = getCookie("mr_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const controller = new AbortController();
  let timeoutId: number | undefined;
  let removeAbortListener: (() => void) | undefined;

  if (init.signal) {
    if (init.signal.aborted) {
      controller.abort(init.signal.reason);
    } else {
      const abort = () => controller.abort(init.signal?.reason);
      init.signal.addEventListener("abort", abort, { once: true });
      removeAbortListener = () => init.signal?.removeEventListener("abort", abort);
    }
  }

  timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        `The application server did not respond within ${REQUEST_TIMEOUT_MS / 1000} seconds. Check the API deployment and try again.`,
        0,
      );
    }
    throw new ApiError("Unable to reach the application server. Check your connection and try again.", 0);
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    removeAbortListener?.();
  }

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function register(email: string, password: string): Promise<User> {
  return request<User>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<User> {
  return request<User>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function requestPasswordReset(email: string): Promise<string> {
  const response = await request<{ message: string }>("/api/auth/password-reset/request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  return response.message;
}

export async function confirmPasswordReset(accessToken: string, password: string): Promise<string> {
  const response = await request<{ message: string }>("/api/auth/password-reset/confirm", {
    method: "POST",
    body: JSON.stringify({ access_token: accessToken, password }),
  });
  return response.message;
}

export async function getCurrentUser(): Promise<User> {
  return request<User>("/api/auth/me");
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
}

export async function getQuotes(symbols: string[], refresh = false): Promise<Quote[]> {
  const params = new URLSearchParams({
    symbols: symbols.join(","),
    refresh: String(refresh),
  });

  const body = await request<{ quotes: Quote[] }>(`/api/market/quotes?${params}`);
  return body.quotes;
}

export async function getWatchlists(): Promise<Watchlist[]> {
  const body = await request<{ watchlists: Watchlist[] }>("/api/watchlists");
  return body.watchlists;
}

export async function createWatchlist(name: string): Promise<Watchlist> {
  return request<Watchlist>("/api/watchlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function renameWatchlist(id: string, name: string): Promise<Watchlist> {
  return request<Watchlist>(`/api/watchlists/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export async function deleteWatchlist(id: string): Promise<void> {
  await request<void>(`/api/watchlists/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function addWatchlistSymbol(id: string, symbol: string): Promise<WatchlistItem> {
  return request<WatchlistItem>(`/api/watchlists/${encodeURIComponent(id)}/symbols`, {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
}

export async function removeWatchlistSymbol(id: string, symbol: string): Promise<void> {
  await request<void>(
    `/api/watchlists/${encodeURIComponent(id)}/symbols/${encodeURIComponent(symbol)}`,
    { method: "DELETE" },
  );
}
