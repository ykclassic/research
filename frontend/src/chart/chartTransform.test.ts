import { describe, expect, it } from "vitest";
import { toChartDataset } from "./chartTransform";
import type { TechnicalAnalysis } from "../api";

function analysis(overrides: Partial<TechnicalAnalysis> = {}): TechnicalAnalysis {
  return {
    symbol: "BTC/USD",
    timeframe: "1h",
    source: "twelve_data",
    calculated_at: "2026-08-29T00:00:00Z",
    latest_candle_timestamp: "2026-08-29T02:00:00Z",
    candle_count: 3,
    candles: [
      { timestamp: "2026-08-29T00:00:00Z", open: 100, high: 105, low: 99, close: 103, volume: 10, is_complete: true },
      { timestamp: "2026-08-29T01:00:00Z", open: 103, high: 107, low: 101, close: 102, volume: 12, is_complete: true },
      { timestamp: "2026-08-29T02:00:00Z", open: 102, high: 108, low: 100, close: 106, volume: 15, is_complete: true },
    ],
    indicators: { ema20: 104.5, rsi14: 58 },
    ...overrides,
  };
}

describe("toChartDataset", () => {
  it("maps completed OHLCV values and keeps volume on the same timestamps", () => {
    const result = toChartDataset(analysis());
    expect(result.candles).toHaveLength(3);
    expect(result.candles[0]).toMatchObject({ open: 100, high: 105, low: 99, close: 103 });
    expect(result.volume.map(item => item.time)).toEqual(result.candles.map(item => item.time));
    expect(result.priceLines).toEqual([{ id: "ema20", title: "EMA 20", price: 104.5 }]);
  });

  it("excludes forming candles from the chart", () => {
    const result = toChartDataset(analysis({
      candle_count: 2,
      latest_candle_timestamp: "2026-08-29T01:00:00Z",
      candles: [
        analysis().candles[0],
        analysis().candles[1],
        { ...analysis().candles[2], is_complete: false },
      ],
    }));
    expect(result.candles).toHaveLength(2);
    expect(result.volume).toHaveLength(2);
  });

  it("rejects duplicate or descending timestamps", () => {
    expect(() => toChartDataset(analysis({ candles: [analysis().candles[0], { ...analysis().candles[1], timestamp: analysis().candles[0].timestamp }] }))).toThrow(/strictly increasing/);
  });

  it("rejects malformed OHLC relationships", () => {
    expect(() => toChartDataset(analysis({ candles: [{ ...analysis().candles[0], high: 101 }, analysis().candles[1], analysis().candles[2]] }))).toThrow(/Invalid OHLC relationship/);
  });

  it("rejects non-positive prices and empty completed data", () => {
    expect(() => toChartDataset(analysis({ candles: [{ ...analysis().candles[0], close: 0 }, analysis().candles[1], analysis().candles[2]] }))).toThrow(/positive/);
    expect(() => toChartDataset(analysis({ candles: analysis().candles.map(candle => ({ ...candle, is_complete: false })) }))).toThrow(/No completed candles/);
  });

  it("does not fabricate a volume value when the provider omits volume", () => {
    const result = toChartDataset(analysis({ candles: [{ ...analysis().candles[0], volume: null }, analysis().candles[1], analysis().candles[2]] }));
    expect(result.volume).toHaveLength(2);
  });
});
