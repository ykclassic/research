import type { TechnicalAnalysis } from "../api";
import type { UTCTimestamp } from "lightweight-charts";
import type { ChartCandle, ChartDataset, ChartIndicatorPane, ChartPriceLine, ChartVolumeBar } from "./chartTypes";

function toTime(timestamp: string): UTCTimestamp {
  const milliseconds = Date.parse(timestamp);
  if (!Number.isFinite(milliseconds)) {
    throw new Error(`Invalid candle timestamp: ${timestamp}`);
  }

  const seconds = Math.floor(milliseconds / 1000);
  if (!Number.isSafeInteger(seconds) || seconds < 0) {
    throw new Error(`Invalid candle timestamp: ${timestamp}`);
  }

  return seconds as UTCTimestamp;
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

function toIndicatorPanes(data: TechnicalAnalysis): ChartIndicatorPane[] {
  if (!Array.isArray(data.indicator_panes)) {
    throw new Error("Technical-analysis indicator panes must be an array.");
  }

  return data.indicator_panes.map(pane => {
    if (!pane.id || !pane.title || !pane.unit || !Array.isArray(pane.points)) {
      throw new Error("Technical-analysis indicator pane has an invalid contract.");
    }

    const points = pane.points.map(point => ({
      time: toTime(point.timestamp),
      value: finiteNumber(point.value, `${pane.id}.value`),
    }));

    for (let index = 1; index < points.length; index += 1) {
      if (points[index].time <= points[index - 1].time) {
        throw new Error(`Indicator pane ${pane.id} is not strictly increasing by timestamp.`);
      }
    }

    return {
      id: pane.id,
      title: pane.title,
      unit: pane.unit,
      min: pane.min,
      max: pane.max,
      points,
    };
  });
}

export function toChartDataset(data: TechnicalAnalysis): ChartDataset {
  if (!Array.isArray(data.candles)) {
    throw new Error("Technical-analysis candles must be an array.");
  }

  const candles: ChartCandle[] = [];
  const volume: ChartVolumeBar[] = [];
  let previousTime: UTCTimestamp | null = null;

  for (const candle of data.candles) {
    if (!candle.is_complete) continue;

    const time = toTime(candle.timestamp);
    if (previousTime !== null && time <= previousTime) {
      throw new Error("Chart candles are not strictly increasing by timestamp.");
    }

    const open = finiteNumber(candle.open, "open");
    const high = finiteNumber(candle.high, "high");
    const low = finiteNumber(candle.low, "low");
    const close = finiteNumber(candle.close, "close");

    if (open <= 0 || high <= 0 || low <= 0 || close <= 0) {
      throw new Error(`Candle prices must be positive at ${candle.timestamp}.`);
    }

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
    indicatorPanes: toIndicatorPanes(data),
  };
}
