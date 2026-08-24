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

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

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

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message);
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

export async function getCurrentUser(): Promise<User> {
  return request<User>("/api/auth/me");
}

export async function logout(): Promise<void> {
  await request<void>("/api/auth/logout", { method: "POST" });
}

export async function getQuotes(
  symbols: string[],
  refresh = false,
): Promise<Quote[]> {
  const params = new URLSearchParams({
    symbols: symbols.join(","),
    refresh: String(refresh),
  });

  const body = await request<{ quotes: Quote[] }>(`/api/market/quotes?${params}`);
  return body.quotes;
}
