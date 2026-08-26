# Phase 3.9 — Performance & Reliability

## Objective

Keep the deterministic market-analysis path responsive and bounded without changing canonical numerical results.

## Implemented controls

- Analysis provider calls are bounded by `ANALYSIS_TIMEOUT_SECONDS` (default 10 seconds).
- Provider timeout is converted to an explicit `503` response rather than allowing an unbounded request.
- API responses continue to use `Cache-Control: no-store`; frontend refresh remains authoritative for fresh analysis.
- `Server-Timing` exposes server-side application duration for production latency measurement without exposing provider credentials or payloads.
- Deterministic analysis results are regression-tested across repeated identical requests.
- Existing quote aggregation remains concurrently fetched with an 8-second per-symbol bound.
- Existing short-lived quote cache remains limited to live quotes.
- Existing MACD optimization calculates EMA histories once rather than repeatedly recalculating growing prefixes.

## Reliability invariants

1. Provider latency cannot block an analysis request indefinitely.
2. Timeout failures return an explicit `503` and do not produce synthetic market data.
3. A performance change must not alter deterministic indicator values.
4. Analysis metadata remains derived from the canonical serialized candle set.
5. API responses remain non-cacheable by browsers/intermediaries.
6. Latency measurement is available through `Server-Timing`.

## Acceptance criteria

- Full backend test suite passes.
- Frontend production build passes.
- Timeout behavior is covered by automated tests.
- Server timing is present on health and analysis responses.
- Repeated identical deterministic analysis produces identical indicator values and candle metadata.
- Production analysis remains within the configured latency budget or returns a bounded `503`.
- No stale/synthetic data is returned on provider timeout.
- Production latency is measured from the deployed API before Phase 3.9 is certified.
