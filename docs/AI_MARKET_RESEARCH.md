# AI Market Research

## Deterministic-first contract

AI Market Research is an interpretation layer, not a market-data layer.

The request path is:

```text
Market Data
    ↓
Feature Engine
    ↓
Deterministic Technical Analysis + Market Structure
    ↓
Research Context
    ↓
AI Interpretation
    ↓
Human-readable report
```

The AI endpoint runs the existing deterministic analysis, regime, market-structure, and multi-timeframe layers on the server before calling the AI provider. The client cannot submit its own market facts as AI context.

The AI layer is explicitly prohibited from being the source of truth for:

- prices
- provider timestamps
- indicators
- historical candles
- market status
- calculated statistics

The UI keeps the verified deterministic context separate from the AI prose so users can distinguish evidence from interpretation.

## Research gate

`POST /api/ai-research/report` returns `409` instead of invoking the AI provider when deterministic technical analysis is not research-eligible, when the analysis and market-structure snapshots are temporally misaligned, or when the MTF context is incomplete.

The endpoint also requires the authenticated session and CSRF token.

## AI provider

The backend uses the OpenAI Responses API from the server. `OPENAI_API_KEY` is never exposed to the browser. Configure:

- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.6-luna`)
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_OUTPUT_TOKENS`

The request sets `store=false` so the application does not request response storage. The AI provider documentation confirms the Responses API supports the `responses` endpoint and server-side API-key usage.

## UI

Authenticated users receive an **AI Market Research** tab trigger. Opening it presents the report generator, deterministic gate state, human-readable interpretation, and a compact list of the evidence blocks supplied to the model.

The AI tab does not replace the existing Market Data, Technical Analysis, Market Structure, MTF Analysis, or Signals views.
