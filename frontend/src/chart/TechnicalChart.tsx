import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import type { TechnicalAnalysis } from "../api";
import { toChartDataset } from "./chartTransform";

interface TechnicalChartProps {
  data: TechnicalAnalysis;
  height?: number;
}

const CHART_HEIGHT = 520;
type VisibleLogicalRange = { from: number; to: number };

export default function TechnicalChart({ data, height = CHART_HEIGHT }: TechnicalChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [showOverlays, setShowOverlays] = useState(true);

  const transformed = useMemo(() => {
    try {
      return { dataset: toChartDataset(data), error: null as string | null };
    } catch (error) {
      return {
        dataset: null,
        error: error instanceof Error ? error.message : "The API returned malformed chart data.",
      };
    }
  }, [data]);

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
    });

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      borderVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candles;
    volumeSeriesRef.current = volume;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    if (!chart || !candles || !volume || !transformed.dataset) return;

    const previousRange = chart.timeScale().getVisibleLogicalRange() as VisibleLogicalRange | null;

    candles.setData(transformed.dataset.candles);
    volume.setData(transformed.dataset.volume);

    for (const line of candles.priceLines()) candles.removePriceLine(line);
    if (showOverlays) {
      for (const line of transformed.dataset.priceLines) {
        candles.createPriceLine({
          price: line.price,
          title: line.title,
          axisLabelVisible: true,
          lineWidth: 1,
        });
      }
    }

    volume.applyOptions({ visible: showVolume });
    chart.priceScale("volume").applyOptions({
      scaleMargins: showVolume ? { top: 0.82, bottom: 0 } : { top: 1, bottom: 0 },
    });

    if (previousRange) chart.timeScale().setVisibleLogicalRange(previousRange);
    else chart.timeScale().fitContent();
  }, [transformed.dataset, showOverlays, showVolume]);

  function resetView(): void {
    chartRef.current?.timeScale().fitContent();
  }

  if (transformed.error) {
    return (
      <div className="technical-chart-error" role="alert">
        <strong>Chart data validation failed.</strong>
        <span>{transformed.error}</span>
      </div>
    );
  }

  return (
    <div className="technical-chart-shell">
      <div className="technical-chart-header">
        <div>
          <strong>{data.symbol}</strong>
          <span>{data.timeframe} · {transformed.dataset?.candles.length ?? 0} completed candles</span>
        </div>
        <span>{data.source} · API data</span>
      </div>
      <div className="technical-chart-toolbar" role="toolbar" aria-label="Chart controls">
        <button type="button" className={showVolume ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowVolume(value => !value)} aria-pressed={showVolume}>
          Volume
        </button>
        <button type="button" className={showOverlays ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowOverlays(value => !value)} aria-pressed={showOverlays}>
          Overlays
        </button>
        <button type="button" className="chart-toggle" onClick={resetView}>
          Reset view
        </button>
        <span className="chart-hint">Scroll/pinch to zoom · drag to pan · crosshair follows pointer</span>
      </div>
      <div
        ref={containerRef}
        className="technical-chart"
        style={{ height }}
        role="img"
        aria-label={`${data.symbol} ${data.timeframe} candlestick and volume chart`}
      />
    </div>
  );
}
