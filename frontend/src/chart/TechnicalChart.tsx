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

interface TechnicalChartProps {
  data: TechnicalAnalysis;
  height?: number;
}

const CHART_HEIGHT = 620;
type PaneSeries = ISeriesApi<"Line"> | ISeriesApi<"Histogram">;

export default function TechnicalChart({ data, height = CHART_HEIGHT }: TechnicalChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const paneSeriesRef = useRef<PaneSeries[]>([]);
  const [showVolume, setShowVolume] = useState(true);
  const [showOverlays, setShowOverlays] = useState(true);
  const [showRsi, setShowRsi] = useState(true);
  const [showMacd, setShowMacd] = useState(true);

  const dataset = useMemo(() => toChartDataset(data), [data]);

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
      paneSeriesRef.current = [];
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    const candles = candleSeriesRef.current;
    const volume = volumeSeriesRef.current;
    if (!chart || !candles || !volume) return;

    candles.setData(dataset.candles);
    volume.setData(dataset.volume);

    for (const line of candles.priceLines()) candles.removePriceLine(line);
    if (showOverlays) {
      for (const line of dataset.priceLines) {
        candles.createPriceLine({
          price: line.price,
          title: line.title,
          axisLabelVisible: true,
          lineWidth: 1,
        });
      }
    }

    for (const series of paneSeriesRef.current) chart.removeSeries(series);
    paneSeriesRef.current = [];

    const rsi = dataset.indicatorPanes.find(pane => pane.id === "rsi14");
    const macd = dataset.indicatorPanes.filter(pane => pane.id.startsWith("macd"));

    if (showRsi && rsi) {
      const series = chart.addSeries(LineSeries, {
        title: rsi.title,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      }, 1);
      series.setData(rsi.points);
      series.priceScale().applyOptions({
        autoScale: true,
        scaleMargins: { top: 0.15, bottom: 0.15 },
      });
      paneSeriesRef.current.push(series);
    }

    if (showMacd && macd.length > 0) {
      const macdPane = macd.find(pane => pane.id === "macd");
      const signalPane = macd.find(pane => pane.id === "macd_signal");
      const histogramPane = macd.find(pane => pane.id === "macd_histogram");
      if (macdPane) {
        const series = chart.addSeries(LineSeries, {
          title: macdPane.title,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: true,
        }, 2);
        series.setData(macdPane.points);
        paneSeriesRef.current.push(series);
      }
      if (signalPane) {
        const series = chart.addSeries(LineSeries, {
          title: signalPane.title,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
        }, 2);
        series.setData(signalPane.points);
        paneSeriesRef.current.push(series);
      }
      if (histogramPane) {
        const series = chart.addSeries(HistogramSeries, {
          title: histogramPane.title,
          priceLineVisible: false,
          lastValueVisible: false,
        }, 2);
        series.setData(histogramPane.points);
        paneSeriesRef.current.push(series);
      }
    }

    volume.applyOptions({ visible: showVolume });
    chart.priceScale("volume").applyOptions({
      scaleMargins: showVolume ? { top: 0.82, bottom: 0 } : { top: 1, bottom: 0 },
    });
    chart.timeScale().fitContent();
  }, [dataset, showOverlays, showVolume, showRsi, showMacd]);

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
        <span>Lightweight Charts</span>
      </div>
      <div className="technical-chart-toolbar" role="toolbar" aria-label="Chart controls">
        <button type="button" className={showVolume ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowVolume(value => !value)} aria-pressed={showVolume}>
          Volume
        </button>
        <button type="button" className={showOverlays ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowOverlays(value => !value)} aria-pressed={showOverlays}>
          Overlays
        </button>
        <button type="button" className={showRsi ? "chart-toggle active" : "chart-toggle"} onClick={() => setShowRsi(value => !value)} aria-pressed={showRsi}>
          RSI
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
    </div>
  );
}
