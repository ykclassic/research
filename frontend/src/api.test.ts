import { afterEach, describe, expect, it, vi } from "vitest";
import { createAIResearchReport, getTechnicalAnalysis } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("getTechnicalAnalysis", () => {
  it("requests the historical range from the backend without local filtering", async () => {
    const response = {
      symbol: "BTC/USD",
      timeframe: "1h",
      source: "twelve_data",
      calculated_at: "2026-08-29T00:00:00Z",
      latest_candle_timestamp: "2026-08-29T02:00:00Z",
      candle_count: 1,
      candles: [{ timestamp: "2026-08-29T02:00:00Z", open: 100, high: 101, low: 99, close: 100.5, volume: 10, is_complete: true }],
      current_quote: {
        symbol: "BTC/USD",
        provider_symbol: "BTC/USD",
        price: 100.75,
        currency: "USD",
        timestamp: "2026-08-29T02:01:00Z",
        source: "twelve_data",
        status: "LIVE",
        market_open: true,
        latency_ms: 100,
        error: null,
      },
      indicators: {},
      indicator_panes: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await getTechnicalAnalysis("BTC/USD", "1h", 250, {
      startDate: "2026-08-01T00:00:00Z",
      endDate: "2026-08-03T23:59:59Z",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("timeframe=1h");
    expect(url).toContain("start=2026-08-01T00%3A00%3A00Z");
    expect(url).toContain("end=2026-08-03T23%3A59%3A59Z");
    expect(url).not.toContain("limit=250");
    expect(result).toEqual(response);
  });
});

describe("createAIResearchReport", () => {
  it("obtains and sends the CSRF token before posting the report request", async () => {
    vi.stubGlobal("document", { cookie: "" });
    vi.stubGlobal("window", {
      sessionStorage: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
    });

    const csrfToken = "csrf-test-token";
    const response = {
      symbol: "BTC/USD",
      timeframe: "1h",
      deterministic_gate: "PASSED",
      verified_context: {},
      report: "Verified interpretation.",
      model: "gpt-5.6-luna",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "CSRF token issued." }), {
        status: 200,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));

    const result = await createAIResearchReport("BTC/USD", "1h", 250, "How's BTC doing today");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/auth/csrf");
    const [, init] = fetchMock.mock.calls[1];
    expect((init?.headers as Headers).get("X-CSRF-Token")).toBe(csrfToken);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      symbol: "BTC/USD",
      timeframe: "1h",
      limit: 250,
      question: "How's BTC doing today",
    });
    expect(result).toEqual(response);
  });
});
