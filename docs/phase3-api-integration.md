# Phase 3.5 — Technical Analysis API Integration

## Objective

Verify that the `/api/analysis/{symbol}` endpoint is an authoritative integration boundary between provider-sourced canonical OHLCV data, the deterministic FeatureEngine, and the frontend.

## Contract

The endpoint must:

1. Require the existing authenticated session.
2. Normalize the requested symbol through the existing symbol registry.
3. Pass the requested `Timeframe` and bounded `limit` to the market-data provider.
4. Accept the canonical `OHLCVDataset` returned by the provider.
5. Calculate indicators exclusively through `feature_engine.calculate_feature_set()`.
6. Return canonical provenance:
   - symbol
   - timeframe
   - source
   - calculated_at
   - latest_candle_timestamp
   - candle_count
7. Return the provider candles with explicit `is_complete` state.
8. Never use a forming candle in deterministic indicator calculations.
9. Return `422` for invalid timeframe/limit parameters.
10. Map provider or feature-engine validation failures to `503` without exposing internal tracebacks.

## Integration path

```text
Authenticated frontend
        ↓
GET /api/analysis/{symbol}
        ↓
Symbol normalization
        ↓
TwelveDataProvider.get_candles()
        ↓
Validated OHLCVDataset
        ↓
FeatureEngine.calculate()
        ↓
TechnicalAnalysisResult
        ↓
AnalysisResponse
        ↓
Frontend technical-analysis workspace
```

## Forming-candle rule

The response may contain a final forming candle when supplied by the provider. `candle_count` and `latest_candle_timestamp` refer to completed candles used by the FeatureEngine, not merely the number and timestamp of returned provider observations.

## Frontend contract

The TypeScript API model now represents the complete backend response, including `calculated_at`, `latest_candle_timestamp`, `candle_count`, and `Candle.is_complete`. The technical-analysis page displays these provenance fields and distinguishes forming observations from completed candles.

## Test coverage

The integration suite verifies:

- authentication enforcement;
- provider symbol/timeframe/limit propagation;
- canonical response fields;
- deterministic indicator output through the real FeatureEngine;
- forming-candle exclusion;
- invalid timeframe rejection;
- invalid limit rejection;
- provider failure mapping to `503`;
- feature-engine failure mapping to `503`.

## Phase gate

Phase 3.5 is not complete until backend tests and frontend build pass in CI and the deployed endpoint is live-verified against a real authenticated request.
