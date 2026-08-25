# Phase 3.4 — Canonical Deterministic Feature Engine

## Purpose

Phase 3.4 establishes one deterministic feature-engine entry point for all downstream research phases.

```text
Provider OHLCV
    ↓
Canonical OHLCVDataset
    ↓
FeatureEngine
    ↓
Completed-candle selection
    ↓
Pure indicator calculations
    ↓
TechnicalAnalysisResult
    ↓
Research / API / future regime engine
```

## Rules

1. The feature engine performs no network I/O.
2. Provider access remains outside the feature engine.
3. The engine accepts only the canonical `OHLCVDataset` contract.
4. Only completed candles enter indicator calculations.
5. A forming candle may occur only at the end of the dataset.
6. The minimum default history is 20 completed candles.
7. Numerical calculations remain deterministic and side-effect free.
8. Dataset provenance is retained in `TechnicalAnalysisResult`.
9. The API uses `feature_engine.calculate_feature_set()` rather than calling provider data and indicator calculations independently.
10. Existing `calculate_indicators()` remains a pure numerical compatibility layer; it does not prepare datasets or perform I/O.

## Performance boundary

The engine performs dataset preparation once and calculates the complete indicator set from that prepared sequence. Downstream phases should consume the resulting feature set rather than recalculate the same indicators independently.

## Failure behavior

The engine rejects:

- fewer than the configured minimum completed candles;
- incomplete candles occurring before the final dataset position;
- datasets containing no completed candles.

Provider failures, authentication failures, caching, and network retries are intentionally outside this layer.
