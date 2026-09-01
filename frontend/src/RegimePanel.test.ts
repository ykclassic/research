import { describe, expect, it } from "vitest";
import { MarketRegime, RegimeResult } from "./api";
import { validateRegimeResponse } from "./RegimePanel";

const base: RegimeResult = {
  symbol: "BTC/USD",
  timeframe: "1h",
  source: "twelve_data",
  calculated_at: "2026-09-01T18:00:00Z",
  provider_timestamp: "2026-09-01T17:59:00Z",
  latest_candle_timestamp: "2026-09-01T17:00:00Z",
  candle_count: 249,
  regime: "RANGE" as MarketRegime,
  confidence: 0.817596,
  evidence: {
    price: 78097.8,
    ema_50: 78100,
    ema_200: 78200,
    price_above_ema_200: false,
    ema_50_above_ema_200: false,
    adx: 19.2,
    atr: 420,
    atr_percent: 0.00537,
    atr_percentile: 0.42,
    bb_width: 0.018,
    bb_width_percentile: 0.31,
    trend_direction: "NEUTRAL",
    trend_persistence: 0.21,
    directional_move_ratio: 0.12,
  },
  thresholds: {
    adx_strong: 25,
    persistence_strong: 0.7,
    persistence_weak: 0.5,
    directional_ratio_strong: 0.55,
    directional_ratio_weak: 0.25,
    volatility_high_percentile: 0.8,
    volatility_low_percentile: 0.2,
  },
  rule_id: "R7",
  rule: "Directional movement remains below the range threshold after trend and volatility checks.",
};

describe("validateRegimeResponse", () => {
  it("accepts a canonical production regime result", () => {
    expect(validateRegimeResponse(base, "BTC/USD", "1h")).toEqual(base);
  });

  it("rejects symbol or timeframe mismatches", () => {
    expect(() => validateRegimeResponse(base, "ETH/USD", "1h")).toThrow("instead of ETH/USD");
    expect(() => validateRegimeResponse(base, "BTC/USD", "4h")).toThrow("timeframe 1h instead of 4h");
  });

  it("rejects missing provider provenance", () => {
    expect(() => validateRegimeResponse({ ...base, provider_timestamp: null }, "BTC/USD", "1h"))
      .toThrow("incomplete provenance metadata");
  });

  it("rejects confidence outside the canonical range", () => {
    expect(() => validateRegimeResponse({ ...base, confidence: 1.01 }, "BTC/USD", "1h"))
      .toThrow("outside the [0, 1] contract");
  });
});
