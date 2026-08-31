# Phase 5.2 — Regime Classification / Rules Validation

## Objective

Prove that the regime engine classifies market states from measurable evidence rather than merely returning a syntactically valid label.

## Canonical classes

1. `STRONG_TREND_UP`
2. `STRONG_TREND_DOWN`
3. `WEAK_TREND`
4. `RANGE`
5. `HIGH_VOLATILITY`
6. `LOW_VOLATILITY`
7. `UNKNOWN`

## Deterministic rule hierarchy

Rules are mutually exclusive and evaluated in this order:

1. **Unknown** when required evidence is unavailable or the input contract is not sufficient.
2. **Strong trend** when ADX is at least 25, trend persistence is at least 0.70, directional move ratio is at least 0.55, and the net direction is up or down.
3. **Weak trend** when ADX is below 25, persistence is at least 0.60, directional move ratio is at least 0.25, and the net direction is up or down.
4. **High volatility** when ATR percentile or Bollinger-width percentile is at least 0.80.
5. **Low volatility** when both ATR and Bollinger-width percentiles are at most 0.20.
6. **Range** when ADX is below 20 and trend persistence is below 0.60.
7. Otherwise the result is `UNKNOWN` rather than forcing a label.

## Evidence contract

Every non-unknown result carries:

- current completed-candle price
- EMA-50 and EMA-200
- price-vs-EMA-200 relationship
- EMA-50-vs-EMA-200 relationship
- ADX
- ATR and normalized ATR percentage
- ATR empirical percentile
- Bollinger Band width and empirical percentile
- trend direction
- trend persistence
- directional move ratio
- the exact rule that produced the label
- bounded confidence in `[0, 1]`

## Validation gate

The automated suite must demonstrate:

- all seven regimes are reachable from controlled synthetic OHLCV paths;
- classification is deterministic for identical input;
- evidence is populated and bounded;
- insufficient history is rejected;
- forming candles are rejected;
- no provider, network, cache, quote, or AI dependency is involved in classification.

Phase 5.2 is **not** production-certified by this unit suite alone. Production certification requires the later Phase 5 gates, including integration, performance, security, and live verification.
