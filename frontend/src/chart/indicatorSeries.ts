import type { TechnicalAnalysis } from "../api";
import type { UTCTimestamp } from "lightweight-charts";

export interface ChartPoint {
  time: UTCTimestamp;
  value: number;
}

export interface HistogramPoint extends ChartPoint {
  color?: string;
}

export interface IndicatorSeries {
  ema20: ChartPoint[];
  ema50: ChartPoint[];
  ema200: ChartPoint[];
  bbUpper: ChartPoint[];
  bbLower: ChartPoint[];
  vwap: ChartPoint[];
  rsi: ChartPoint[];
  macd: ChartPoint[];
  macdSignal: ChartPoint[];
  macdHistogram: HistogramPoint[];
}

interface NumericCandle {
  time: UTCTimestamp;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

function toTime(timestamp: string): UTCTimestamp {
  const milliseconds = Date.parse(timestamp);
  if (!Number.isFinite(milliseconds)) {
    throw new Error(`Invalid candle timestamp: ${timestamp}`);
  }
  return Math.floor(milliseconds / 1000) as UTCTimestamp;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function ema(values: number[], period: number): Array<number | null> {
  const output: Array<number | null> = Array.from({ length: values.length }, () => null);
  if (values.length < period || period < 1) return output;

  let sum = 0;
  for (let index = 0; index < period; index += 1) sum += values[index];
  let previous = sum / period;
  output[period - 1] = previous;

  const multiplier = 2 / (period + 1);
  for (let index = period; index < values.length; index += 1) {
    previous = (values[index] - previous) * multiplier + previous;
    output[index] = previous;
  }
  return output;
}

function rsi(values: number[], period = 14): Array<number | null> {
  const output: Array<number | null> = Array.from({ length: values.length }, () => null);
  if (values.length <= period || period < 1) return output;

  let gain = 0;
  let loss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = values[index] - values[index - 1];
    gain += Math.max(change, 0);
    loss += Math.max(-change, 0);
  }

  let averageGain = gain / period;
  let averageLoss = loss / period;
  output[period] = averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss);

  for (let index = period + 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
    output[index] = averageLoss === 0 ? 100 : 100 - 100 / (1 + averageGain / averageLoss);
  }
  return output;
}

function rollingBollinger(values: number[], period = 20, deviations = 2): {
  upper: Array<number | null>;
  lower: Array<number | null>;
} {
  const upper: Array<number | null> = Array.from({ length: values.length }, () => null);
  const lower: Array<number | null> = Array.from({ length: values.length }, () => null);
  if (values.length < period) return { upper, lower };

  for (let index = period - 1; index < values.length; index += 1) {
    const window = values.slice(index - period + 1, index + 1);
    const mean = window.reduce((total, value) => total + value, 0) / period;
    const variance = window.reduce((total, value) => total + (value - mean) ** 2, 0) / period;
    const standardDeviation = Math.sqrt(variance);
    upper[index] = mean + deviations * standardDeviation;
    lower[index] = mean - deviations * standardDeviation;
  }
  return { upper, lower };
}

function toPoints(values: Array<number | null>, candles: NumericCandle[]): ChartPoint[] {
  return values.flatMap((value, index) => value === null || !Number.isFinite(value)
    ? []
    : [{ time: candles[index].time, value }]);
}

export function buildIndicatorSeries(data: TechnicalAnalysis): IndicatorSeries {
  const candles: NumericCandle[] = data.candles
    .filter((candle) => candle.is_complete)
    .map((candle) => ({
      time: toTime(candle.timestamp),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: finite(candle.volume) ? candle.volume : null,
    }));

  const closes = candles.map((candle) => candle.close);
  const ema20 = ema(closes, 20);
  const ema50 = ema(closes, 50);
  const ema200 = ema(closes, 200);
  const rsi14 = rsi(closes, 14);
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const macdValues: Array<number | null> = closes.map((_, index) => {
    if (ema12[index] === null || ema26[index] === null) return null;
    return ema12[index]! - ema26[index]!;
  });
  const macdNumbers = macdValues.filter((value): value is number => value !== null);
  const signalNumbers = ema(macdNumbers, 9);
  const macdSignal: Array<number | null> = Array.from({ length: closes.length }, () => null);
  let signalIndex = 0;
  for (let index = 0; index < macdValues.length; index += 1) {
    if (macdValues[index] === null) continue;
    macdSignal[index] = signalNumbers[signalIndex] ?? null;
    signalIndex += 1;
  }

  const macdHistogram: Array<number | null> = macdValues.map((value, index) => {
    const signal = macdSignal[index];
    return value !== null && signal !== null ? value - signal : null;
  });

  const bollinger = rollingBollinger(closes, 20, 2);
  const vwap: Array<number | null> = [];
  let cumulativePriceVolume = 0;
  let cumulativeVolume = 0;
  for (const candle of candles) {
    if (candle.volume === null) {
      vwap.push(null);
      continue;
    }
    cumulativePriceVolume += ((candle.high + candle.low + candle.close) / 3) * candle.volume;
    cumulativeVolume += candle.volume;
    vwap.push(cumulativeVolume > 0 ? cumulativePriceVolume / cumulativeVolume : null);
  }

  return {
    ema20: toPoints(ema20, candles),
    ema50: toPoints(ema50, candles),
    ema200: toPoints(ema200, candles),
    bbUpper: toPoints(bollinger.upper, candles),
    bbLower: toPoints(bollinger.lower, candles),
    vwap: toPoints(vwap, candles),
    rsi: toPoints(rsi14, candles),
    macd: toPoints(macdValues, candles),
    macdSignal: toPoints(macdSignal, candles),
    macdHistogram: macdHistogram.flatMap((value, index) => value === null || !Number.isFinite(value)
      ? []
      : [{
          time: candles[index].time,
          value,
          color: value >= 0 ? "rgba(38, 166, 154, 0.65)" : "rgba(239, 83, 80, 0.65)",
        }]),
  };
}
