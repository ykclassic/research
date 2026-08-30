import { describe, expect, it } from "vitest";
import { buildRange, toUtcEnd, toUtcStart, validateAnalysisResponse } from "./TechnicalAnalysisPage";
import type { TechnicalAnalysis } from "./api";

const BASE: TechnicalAnalysis = {
  symbol: "BTC/USD",
  timeframe: "1h",
  source: "twelve_data",
  calculated_at: "2026-08-29T00:00:00Z",
  latest_candle_timestamp: "2026-08-29T02:00:00Z",
  candle_count: 3,
  candles: [
    { timestamp: "2026-08-29T00:00:00Z", open: 100, high: 101, low: 99, close: 100.5, volume: 10, is_complete: true },
    { timestamp: "2026-08-29T01:00:00Z", open: 100.5, high: 102, low: 100, close: 101, volume: 11, is_complete: true },
    { timestamp: "2026-08-29T02:00:00Z", open: 101, high: 103, low: 100.5, close: 102, volume: 12, is_complete: true },
  ],
  current_quote: {
    symbol: "BTC/USD",
    provider_symbol: "BTC/USD",
    price: 102.25,
    currency: "USD",
    timestamp: "2026-08-29T02:15:00Z",
    source: "twelve_data",
    status: "LIVE",
    market_open: true,
    latency_ms: 100,
    error: null,
  },
  indicators: {},
  indicator_panes: [],
};

describe("chart range state", () => {
  const now = new Date("2026-08-29T05:15:00Z");

  it("uses the recent API window without local market-data filtering", () => {
    expect(buildRange("recent", now)).toEqual({});
  });

  it("creates API boundaries for a one-week range", () => {
    expect(buildRange("1w", now)).toEqual({
      startDate: "2026-08-23T23:59:59.000Z",
      endDate: "2026-08-29T23:59:59.000Z",
    });
  });

  it("serializes custom dates as UTC server boundaries", () => {
    expect(toUtcStart("2026-08-01")).toBe("2026-08-01T00:00:00Z");
    expect(toUtcEnd("2026-08-03")).toBe("2026-08-03T23:59:59Z");
    expect(buildRange("custom", now, "2026-08-01", "2026-08-03")).toEqual({
      startDate: "2026-08-01T00:00:00Z",
      endDate: "2026-08-03T23:59:59Z",
    });
  });
});

describe("canonical API response validation", () => {
  it("accepts a matching symbol and timeframe", () => {
    expect(validateAnalysisResponse(BASE, "BTC/USD", "1h")).toBe(BASE);
  });

  it("rejects a mismatched timeframe", () => {
    expect(() => validateAnalysisResponse({ ...BASE, timeframe: "5m" }, "BTC/USD", "1h")).toThrow(/timeframe/);
  });

  it("rejects an empty candle response", () => {
    expect(() => validateAnalysisResponse({ ...BASE, candles: [], candle_count: 0 }, "BTC/USD", "1h")).toThrow(/no historical candles/);
  });

  it("rejects a response for the wrong instrument", () => {
    expect(() => validateAnalysisResponse({ ...BASE, symbol: "ETH/USD", current_quote: { ...BASE.current_quote, symbol: "ETH/USD" } }, "BTC/USD", "1h")).toThrow(/instead of BTC\/USD/);
  });
});
