# Phase 4.4 — Functional Gap Closure

## Scope

Phase 4.4 closes the charting contract gaps between the verified market-data API and the research workspace.

### Acceptance criteria

1. **Current quote separation**
   - `GET /api/analysis/{symbol}` obtains the current quote independently from historical OHLCV candles.
   - The response exposes `current_quote` separately from `candles` and `latest_candle_timestamp`.
   - The UI labels the live quote separately from the last completed candle close.
   - The analysis request forces a fresh quote fetch; the chart does not treat the last candle close as the current quote.

2. **Chart controls**
   - Instrument and timeframe selectors remain API-backed.
   - Volume and deterministic price overlays can be toggled.
   - RSI and MACD indicator panes can be toggled.
   - Reset view, crosshair, zoom, pan, mouse-wheel scaling, and touch scaling remain enabled.
   - Forming candles are excluded from chart calculations.

3. **Indicator-pane data contract**
   - Backend returns `indicator_panes` with stable IDs, title, unit, bounds, timestamp, and numeric value fields.
   - Pane timestamps are strictly increasing within each pane.
   - Indicator values are calculated from the same completed-candle set used by the deterministic TA engine.
   - RSI is explicitly bounded to 0–100.
   - Frontend validates and transforms the contract before rendering.

4. **Automated verification**
   - Backend tests verify authentication, current-quote separation, candle/quote provenance, forming-candle exclusion, and indicator-pane integrity.
   - Frontend TypeScript type checking and production build must pass.
   - CI must remain green before the phase is merged.

## Non-goals

- No AI-generated chart values.
- No provider-derived current quote inserted into historical candles.
- No black-box indicator labels.
- No autonomous trading behavior.
