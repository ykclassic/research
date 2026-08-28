import type { TechnicalAnalysis } from "../api";
import type { ChartCandle, ChartDataset, ChartPriceLine, ChartVolumeBar } from "./chartTypes";

function toTime(timestamp: string): number {
  const milliseconds = Date.parse(timestamp);
  if (!Number.isFinite(milliseconds)) throw new Error(`Invalid candle timestamp: ${timestamp}`);
  return Math.floor(milliseconds / 1000);
}

function finiteNumber(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Invalid numeric candle field: ${field}`);
  }
  return value;
}

function toPriceLines(indicators: TechnicalAnalysis["indicators"]): ChartPriceLine[] {
  const definitions: Array<[string, string]> = [
    ["ema20", "EMA 20"],
    ["ema50", "EMA 50"],
    ["ema200", "EMA 200"],
    ["sma20", "SMA 20"],
    ["sma50", "SMA 50"],
    ["sma200", "SMA 200"],
    ["bb_upper", "BB Upper"],
    ["bb_lower", "BB Lower"],
    ["vwap", "VWAP"],
  ];

  return definitions.flatMap(([key, title]) => {
    const price = indicators[key];
    return typeof price === "number" && Number.isFinite(price)
      ? [{ id: key, title, price }]
      : [];
  });
}

export function toChartDataset(data: TechnicalAnalysis): ChartDataset {
  const candles: ChartCandle[] = [];
  const volume: ChartVolumeBar[] = [];
  let previousTime = 0;

  for (const candle of data.candles) {
    if (!candle.is_complete) continue;

    const time = toTime(candle.timestamp);
    if (time <= previousTime) {
      throw new Error("Chart candles are not strictly increasing by timestamp.");
    }

    const open = finiteNumber(candle.open, "open");
    const high = finiteNumber(candle.high, "high");
    const low = finiteNumber(candle.low, "low");
    const close = finiteNumber(candle.close, "close");

    if (high < Math.max(open, close) || low > Math.min(open, close) || low > high) {
      throw new Error(`Invalid OHLC relationship at ${candle.timestamp}.`);
    }

    candles.push({ time, open, high, low, close });

    if (typeof candle.volume === "number" && Number.isFinite(candle.volume) && candle.volume >= 0) {
      volume.push({
        time,
        value: candle.volume,
        color: close >= open ? "rgba(38, 166, 154, 0.55)" : "rgba(239, 83, 80, 0.55)",
      });
    }

    previousTime = time;
  }

  if (candles.length === 0) throw new Error("No completed candles are available for charting.");

  return {
    candles,
    volume,
    priceLines: toPriceLines(data.indicators),
  };
}
