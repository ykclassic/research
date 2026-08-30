import type { Time } from "lightweight-charts";

export interface ChartCandle {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartVolumeBar {
  time: Time;
  value: number;
  color?: string;
}

export interface ChartPriceLine {
  id: string;
  title: string;
  price: number;
  lineStyle?: number;
  lineWidth?: number;
}

export interface ChartIndicatorPoint {
  time: Time;
  value: number;
}

export interface ChartIndicatorPane {
  id: string;
  title: string;
  unit: string;
  min: number | null;
  max: number | null;
  points: ChartIndicatorPoint[];
}

export interface ChartDataset {
  candles: ChartCandle[];
  volume: ChartVolumeBar[];
  priceLines: ChartPriceLine[];
  indicatorPanes: ChartIndicatorPane[];
}

export interface ChartViewOptions {
  showVolume: boolean;
  showOverlays: boolean;
  showRsi: boolean;
  showMacd: boolean;
  fitContentOnDataChange: boolean;
}
