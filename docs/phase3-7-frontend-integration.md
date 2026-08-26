# Phase 3.7 — Frontend Integration

## Objective

Provide a production-safe React integration for the canonical Phase 3 technical-analysis API. The browser renders server-derived technical facts and does not calculate indicators independently.

## Integration contract

```text
Production FastAPI
      ↓
GET /api/analysis/{symbol}?timeframe={timeframe}&limit=250
      ↓
Typed frontend API client
      ↓
TechnicalAnalysisPage
      ↓
Provenance + completed-candle metadata + indicators
```

## Acceptance criteria

1. The frontend calls the canonical `/api/analysis/{symbol}` endpoint through `getTechnicalAnalysis()`.
2. Symbol changes request the selected symbol.
3. Timeframe changes request the selected timeframe.
4. Manual refresh requests fresh analysis.
5. Automatic refresh occurs every 60 seconds while the analysis page is mounted.
6. Out-of-order responses cannot overwrite a newer symbol/timeframe selection.
7. The frontend validates returned symbol and timeframe before rendering.
8. The frontend rejects empty candle arrays and invalid completed-candle counts.
9. Provider source, calculation timestamp, latest completed-candle timestamp, and candle counts are required before rendering.
10. Forming candles remain visible as observations but are not used as the displayed latest completed candle.
11. Authentication failures log the user out through the existing authentication boundary.
12. API errors are surfaced with an explicit retry action.
13. Failed refreshes clear the previous result rather than presenting stale technical analysis as current.
14. Indicator values are consumed from the backend response; no frontend indicator calculation is performed.
15. CI must pass the production frontend build.
16. Production deployment must be manually verified before Phase 3.7 is certified.

## Performance considerations

- The page performs one analysis request on mount and one request per 60-second refresh interval.
- The interval is cleaned up when the page unmounts or the symbol/timeframe changes.
- A request sequence guard prevents stale asynchronous responses from overwriting newer selections.
- The frontend renders only the latest 12 candles in the visible recent-candle table.

## Security considerations

- Requests use the existing authenticated API client and `credentials: include` behavior.
- The technical-analysis endpoint remains protected by the backend authentication boundary.
- No provider credentials are exposed to the browser.
- No price or indicator values are hardcoded into the analysis UI.

## Certification evidence

Phase 3.7 requires both CI success and production verification of:

- symbol selection;
- timeframe selection;
- manual refresh;
- automatic refresh;
- provenance metadata;
- completed-candle handling;
- indicator rendering;
- API error handling;
- authenticated access.
