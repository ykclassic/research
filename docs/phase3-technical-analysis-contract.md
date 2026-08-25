# Phase 3.2 — Canonical Technical Analysis Contract

## Purpose

Phase 3 technical analysis is authoritative only when it is calculated from the canonical, validated OHLCV dataset. The frontend must not independently calculate authoritative indicator values.

## Data flow

```text
Provider
  ↓
Provider Adapter
  ↓
Canonical Candle validation
  ↓
OHLCVDataset
  ↓
Completed-candle filter
  ↓
Deterministic TA engine
  ↓
TechnicalAnalysisResult
  ↓
Research API
```

## Canonical candle

Every candle contains:

- `timestamp`: timezone-aware UTC timestamp
- `open`, `high`, `low`, `close`: finite positive prices
- `volume`: finite non-negative volume, or null when the provider does not supply it
- `symbol`: canonical internal symbol
- `timeframe`: one of the supported canonical timeframes
- `source`: provider identifier
- `is_complete`: explicit completion state

OHLC invariants are enforced:

```text
high >= max(open, close)
low  <= min(open, close)
high >= low
```

## Dataset invariants

An `OHLCVDataset` must:

1. contain at least one candle;
2. contain strictly increasing timestamps;
3. contain candles with matching symbol, timeframe, and source;
4. use timezone-aware UTC metadata;
5. preserve explicit completion state.

## Completed-candle rule

Authoritative technical indicators are calculated only from candles where `is_complete == true`.

A currently forming candle may be returned for charting, but it must not silently affect finalized technical-analysis values.

## Timeframe contract

Supported canonical timeframes in Phase 3.2:

- `5m`
- `15m`
- `30m`
- `1h`
- `4h`
- `1d`

The timeframe is part of the dataset identity and every candle must match it.

## Technical-analysis result provenance

Every deterministic TA result exposes:

- symbol
- timeframe
- source
- calculation timestamp
- latest completed candle timestamp
- number of completed candles used
- indicator values

This makes the calculation reproducible against the source dataset.

## Indicator methodology

The current Phase 3 engine retains the existing deterministic implementations for:

- SMA
- EMA
- RSI
- MACD
- Bollinger Bands
- ATR
- ADX
- Stochastic
- VWAP
- OBV

Numerical reference validation of each implementation is a separate Phase 3 acceptance task. The implementation must not be considered certified solely because the indicator name is present or because a calculation returns a value.

## VWAP

The current implementation defines the session as the UTC calendar date represented by the latest candle and calculates volume-weighted typical price:

```text
typical_price = (high + low + close) / 3
VWAP = sum(typical_price × volume) / sum(volume)
```

This definition must remain explicit. Asset-class-specific session semantics should not be introduced implicitly.

## Provider contract

All market-data providers must implement:

```text
get_quote(symbol)
get_candles(symbol, timeframe, outputsize)
health()
```

Provider-specific candle representations must be normalized into the canonical `OHLCVDataset` before research calculations consume them.

## Non-goals of Phase 3.2

Phase 3.2 does not yet introduce:

- market-regime detection;
- SMC/ICT structure detection;
- multi-timeframe research conclusions;
- AI interpretation;
- autonomous trading decisions.

Those belong to later phases.
