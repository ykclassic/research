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

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export async function getQuotes(
  symbols: string[],
  refresh = false,
): Promise<Quote[]> {
  const params = new URLSearchParams({
    symbols: symbols.join(","),
    refresh: String(refresh),
  });

  const response = await fetch(`${API_BASE}/api/market/quotes?${params}`);
  if (!response.ok) {
    throw new Error(`Quote request failed: ${response.status}`);
  }

  const body = (await response.json()) as { quotes: Quote[] };
  return body.quotes;
}
