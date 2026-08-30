# Phase 4.5 — Chart Workspace Completion

## Objective

Extend the verified Phase 4.4 chart shell into a controlled research workspace without moving market-data authority into the browser.

## Implemented scope

1. **Server-side historical ranges**
   - `GET /api/analysis/{symbol}` accepts timezone-aware `start` and `end` boundaries.
   - The backend forwards those boundaries to the canonical Twelve Data time-series provider.
   - `start` and `end` must be supplied together and `start < end`.
   - The browser never downloads a larger dataset and locally filters it.
   - Twelve Data's documented contract supports `start_date` + `end_date` for bounded historical time series and omits `outputsize` when both are supplied.

2. **Workspace range controls**
   - Recent API window
   - 1 day
   - 1 week
   - 1 month
   - 3 months
   - Custom start/end dates

3. **Refresh state**
   - 60-second auto-refresh can be enabled or disabled.
   - Refresh does not clear already-rendered data while a request is in flight.
   - Request sequencing continues to prevent an older response replacing a newer request.

4. **Viewport preservation**
   - Chart updates preserve the current logical viewport when new API data arrives.
   - Reset view remains available to fit the complete returned dataset.

5. **Live quote separation**
   - The current quote remains sourced from the API's `current_quote` field.
   - The chart renders it as a separate `LIVE` price marker.
   - The historical candle series remains completed-candle data only.

6. **Automated verification**
   - Backend tests verify range validation and provider parameter forwarding.
   - Frontend tests verify range serialization and API response validation.
   - Frontend CI executes the chart/workspace test suite before the production build.

## Non-goals

- No frontend-generated market prices.
- No client-side historical filtering as a substitute for provider queries.
- No AI-generated chart values.
- No autonomous trading.
- No assertion that a historical range is available beyond what the canonical provider actually returns.

## Gate

Phase 4.5 is PASS only when:

- Backend CI is green.
- Frontend chart/workspace tests are green.
- Frontend production build is green.
- Deployed backend accepts and enforces the range contract.
- Deployed frontend requests the selected range from the backend.
- Production market-data verification remains green after deployment.
