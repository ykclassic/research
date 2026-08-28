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
}

export interface ChartDataset {
  candles: ChartCandle[];
  volume: ChartVolumeBar[];
  priceLines: ChartPriceLine[];
}

export interface ChartViewOptions {
  showVolume: boolean;
  showOverlays: boolean;
  fitContentOnDataChange: boolean;
}
