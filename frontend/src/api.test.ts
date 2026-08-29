import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getTechnicalAnalysis } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("getTechnicalAnalysis", () => {
  it("requests timeframe and server-side historical range without locally filtering data", async () => {
    const response = {
      symbol: "BTC/USD",
      timeframe: "1h",
      source: "twelve_data",
      calculated_at: "2026-08-29T00:00:00Z",
      latest_candle_timestamp: "2026-08-29T02:00:00Z",
      candle_count: 1,
      candles: [{ timestamp: "2026-08-29T02:00:00Z", open: 100, high: 101, low: 99, close: 100.5, volume: 10, is_complete: true }],
      indicators: {},
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(response), { status: 200, headers: { "Content-Type": "application/json" } }));

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

  it("surfaces API failures instead of supplying fallback market data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "provider unavailable" }), { status: 503, headers: { "Content-Type": "application/json" } }));

    await expect(getTechnicalAnalysis("BTC/USD", "1h")).rejects.toMatchObject({ status: 503, message: "provider unavailable" });
  });
});
