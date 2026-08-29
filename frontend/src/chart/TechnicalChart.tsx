import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import type { TechnicalAnalysis } from "../api";
import { toChartDataset } from "./chartTransform";
import { buildIndicatorSeries } from "./indicatorSeries";

interface TechnicalChartProps {
  data: TechnicalAnalysis;
  height?: number;
}

const CHART_HEIGHT = 680;

export default function TechnicalChart({ data, height = CHART_HEIGHT }: TechnicalChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const vwapRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistogramRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [showOverlays, setShowOverlays] = useState(true);
  const [showRsi, setShowRsi] = useState(true);
  const [showMacd, setShowMacd] = useState(true);

  const dataset = useMemo(() => toChartDataset(data), [data]);
  const indicators = useMemo(() => buildIndicatorSeries(data), [data]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a9b5c6",
        attributionLogo: true,
        panes: {
          separatorColor: "rgba(148, 163, 184, 0.16)",
          separatorHoverColor: "rgba(148, 163, 184, 0.28)",
        },
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.08)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      crosshair: {
        vertLine: { labelVisible: true },
        horzLine: { labelVisible: true },
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.18)",
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.18)",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
      priceLineVisible: true,
      lastValueVisible: true,
      title: "Price",
      pane: 0,
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
      title: "Volume",
      pane: 0,
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
      borderVisible: false,
    });

    const lineOptions = {
      lineWidth: 1 as const,
      priceLineVisible: false,
      lastValueVisible: false,
      pane: 0,
    };
    const ema20 = chart.addSeries(LineSeries, { ...lineOptions, title: "EMA 20" });
    const ema50 = chart.addSeries(LineSeries, { ...lineOptions, title: "EMA 50" });
    const ema200 = chart.addSeries(LineSeries, { ...lineOptions, title: "EMA 200" });
    const bbUpper = chart.addSeries(LineSeries, { ...lineOptions, title: "BB Upper" });
    const bbLower = chart.addSeries(LineSeries, { ...lineOptions, title: "BB Lower" });
    const vwap = chart.addSeries(LineSeries, { ...lineOptions, title: "VWAP" });

    const rsi = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "RSI (14)",
      pane: 1,
    });
    chart.panes()[1]?.setHeight(120);
    chart.priceScale("rsi").applyOptions({
      autoScale: false,
      scaleMargins: { top: 0.1, bottom: 0.1 },
    });
    rsi.applyOptions({ priceScaleId: "rsi" });
    rsi.createPriceLine({ price: 70, color: "rgba(239, 83, 80, 0.55)", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "70" });
    rsi.createPriceLine({ price: 30, color: "rgba(38, 166, 154, 0.55)", lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "30" });

    const macd = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "MACD",
      pane: 2,
    });
    const macdSignal = chart.addSeries(LineSeries, {
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Signal",
      pane: 2,
    });
    const macdHistogram = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "price", precision: 5, minMove: 0.00001 },
      priceLineVisible: false,
      lastValueVisible: false,
      title: "Histogram",
      pane: 2,
    });
    chart.panes()[2]?.setHeight(120);

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;
    ema20Ref.current = ema20;
    ema50Ref.current = ema50;
    ema200Ref.current = ema200;
    bbUpperRef.current = bbUpper;
    bbLowerRef.current = bbLower;
    vwapRef.current = vwap;
    rsiRef.current = rsi;
    macdRef.current = macd;
    macdSignalRef.current = macdSignal;
    macdHistogramRef.current = macdHistogram;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      bbUpperRef.current = null;
      bbLowerRef.current = null;
      vwapRef.current = null;
      rsiRef.current = null;
      macdRef.current = null;
      macdSignalRef.current = null;
      macdHistogramRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    if (!chart || !candles || !volume) return;

    candles.setData(dataset.candles);
    volume.setData(dataset.volume);
    ema20Ref.current?.setData(indicators.ema20);
    ema50Ref.current?.setData(indicators.ema50);
    ema200Ref.current?.setData(indicators.ema200);
    bbUpperRef.current?.setData(indicators.bbUpper);
    bbLowerRef.current?.setData(indicators.bbLower);
    vwapRef.current?.setData(indicators.vwap);
    rsiRef.current?.setData(indicators.rsi);
    macdRef.current?.setData(indicators.macd);
    macdSignalRef.current?.setData(indicators.macdSignal);
    macdHistogramRef.current?.setData(indicators.macdHistogram);

    volume.applyOptions({ visible: showVolume });
    chart.priceScale("volume").applyOptions({
      scaleMargins: showVolume ? { top: 0.78, bottom: 0 } : { top: 1, bottom: 0 },
    });
    const overlaySeries = [ema20Ref.current, ema50Ref.current, ema200Ref.current, bbUpperRef.current, bbLowerRef.current, vwapRef.current];
    for (const series of overlaySeries) series?.applyOptions({ visible: showOverlays });
    rsiRef.current?.applyOptions({ visible: showRsi });
    macdRef.current?.applyOptions({ visible: showMacd });
    macdSignalRef.current?.applyOptions({ visible: showMacd });
    macdHistogramRef.current?.applyOptions({ visible: showMacd });
    chart.panes()[1]?.setHeight(showRsi ? 120 : 0);
    chart.panes()[2]?.setHeight(showMacd ? 120 : 0);
    chart.timeScale().fitContent();
  }, [dataset, indicators, showMacd, showOverlays, showRsi, showVolume]);

  function resetView(): void {
    chartRef.current?.timeScale().fitContent();
  }

  return (
    <div className="technical-chart-shell">
      <div className="technical-chart-header">
        <div>
          <strong>{data.symbol}</strong>
          <span>{data.timeframe} · {dataset.candles.length} completed candles</span>
        </div>
        <span>Lightweight Charts · deterministic indicator panels</span>
      </div>
      <div className="technical-chart-toolbar" role="toolbar" aria-label="Chart controls">
        <button type="button" className={showVolume ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowVolume(value => !value)} aria-pressed={showVolume}>
          Volume
        </button>
        <button type="button" className={showOverlays ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowOverlays(value => !value)} aria-pressed={showOverlays}>
          Price overlays
        </button>
        <button type="button" className={showRsi ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowRsi(value => !value)} aria-pressed={showRsi}>
          RSI (14)
        </button>
        <button type="button" className={showMacd ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowMacd(value => !value)} aria-pressed={showMacd}>
          MACD
        </button>
        <button type="button" className="chart-toggle" onClick={resetView}>
          Reset view
        </button>
        <span className="chart-hint">Scroll to zoom · drag to pan · crosshair follows pointer</span>
      </div>
      <div
        ref={containerRef}
        className="technical-chart"
        style={{ height }}
        role="img"
        aria-label={`${data.symbol} ${data.timeframe} candlestick, volume, RSI and MACD chart`}
      />
      <div className="chart-provenance">
        <span>Indicators are derived from the same completed provider-sourced candle series.</span>
        <span>RSI: Wilder smoothing · MACD: EMA(12,26,9) · Bollinger: 20-period, 2σ · VWAP: cumulative typical-price volume weighting.</span>
      </div>
    </div>
  );
}
