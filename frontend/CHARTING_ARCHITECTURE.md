# Phase 4.2 — Financial Charting Architecture

## Decision

Use **TradingView Lightweight Charts 5.2.1** as the financial-charting engine.

The package is purpose-built for interactive financial charts, provides built-in TypeScript declarations, uses HTML5 canvas rendering, and exposes candlestick and histogram series plus chart interaction APIs. Version 5 uses the unified `chart.addSeries(SeriesDefinition, options)` API.

## Why this library

- Financial-market data model rather than generic categorical charting.
- Native candlestick series.
- Native histogram series for volume.
- Built-in time scale, crosshair, zoom, pan, and responsive sizing.
- TypeScript declarations included by the package.
- Small dependency footprint relative to general-purpose chart suites.
- Apache-2.0 license.

## Attribution

The chart is configured with the library's TradingView attribution logo. This satisfies the library's documented attribution requirement when retained in the chart. The application should not remove that attribution without replacing it with the required attribution notice/link.

## Component boundary

```text
TechnicalAnalysisPage
        |
        v
TechnicalChart
        |
        +-- chartTransform.ts
        |      |
        |      +-- validate completed OHLCV
        |      +-- convert timestamps to chart time
        |      +-- build volume series
        |      +-- expose latest indicator price levels
        |
        +-- chartTypes.ts
        |      +-- ChartCandle
        |      +-- ChartVolumeBar
        |      +-- ChartPriceLine
        |      +-- ChartDataset
        |
        +-- Lightweight Charts
               +-- CandlestickSeries
               +-- HistogramSeries
               +-- price lines
               +-- crosshair
               +-- time scale
               +-- responsive sizing
```

## Data integrity rules

1. Only completed candles are rendered by the current chart shell.
2. Candle timestamps must parse successfully.
3. Candle timestamps must be strictly increasing.
4. OHLC values must be finite.
5. `high >= max(open, close)` must hold.
6. `low <= min(open, close)` must hold.
7. `low <= high` must hold.
8. Negative or non-finite volume is excluded from the volume series.
9. No indicator history is fabricated from a latest-value API response.
10. Current quote data remains a separate market-data concern and must not be substituted with the last completed candle close.

## Indicator architecture

The current Phase 3 analysis API exposes latest indicator values, not historical indicator series. Therefore the Phase 4.2 implementation represents those values as horizontal price levels where applicable (EMA, SMA, Bollinger boundaries, VWAP).

It deliberately does **not** manufacture historical EMA/SMA/Bollinger/VWAP curves from a scalar latest value.

Phase 4.x should extend the backend contract with historical indicator series before true historical overlay curves are implemented.

## Lifecycle and performance

- One chart instance is created per mounted `TechnicalChart` component.
- The chart is removed on component unmount.
- Data changes update existing series instead of recreating the chart.
- Responsive sizing is delegated to Lightweight Charts `autoSize` support.
- Existing Phase 3 request sequencing remains responsible for preventing stale API responses from replacing newer data.
- Existing 60-second analysis refresh remains unchanged.

## Phase 4.2 scope

Implemented:

- charting dependency;
- chart domain types;
- deterministic API-to-chart transformation;
- completed-candle validation;
- candlestick series;
- volume series;
- crosshair;
- zoom/pan through the chart's native interaction model;
- responsive chart sizing;
- latest indicator price levels;
- TradingView attribution;
- integration into the existing technical-analysis page.

Deferred to subsequent Phase 4 work:

- timeframe toolbar expansion to 1m/1w where backend support exists;
- date-range controls;
- historical indicator overlay series;
- dedicated RSI/MACD/ADX panes;
- live quote marker distinct from last completed candle;
- auto-refresh UI controls;
- chart state persistence;
- advanced drawing/annotation tools.
