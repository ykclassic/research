# News & Fundamental Research

Phase 9 adds a server-side research pipeline for attributed news and structured fundamental events.

## Pipeline

```text
News
  ↓
Event
  ↓
Affected asset
  ↓
Market reaction
  ↓
Technical regime
```

## Data contract

- News items retain provider/source attribution, source URL when supplied, and the provider publication timestamp.
- Entity extraction is restricted to the application's supported canonical asset universe so unsupported tickers are not silently treated as tradable assets.
- Sentiment is a deterministic lexical classification and is presented as research metadata, not a causal market prediction.
- Event classification separates narrative news from earnings, economic, macro, regulatory, and corporate events.
- Earnings and economic calendar records remain structured fundamental events rather than being merged into headline text.
- Market reaction is calculated from validated candle data around the publication timestamp.
- Technical regime is calculated independently from the canonical 1-hour candle dataset.
- Correlation output explicitly represents evidence and timing; it does not claim that a headline caused a price move.

## Endpoint

`GET /api/news/research?symbol=NVDA&days=1&limit=25`

`symbol` is optional. `days` is limited to 1–7 and `limit` to 1–50.

The endpoint requires the same authenticated research session as the other research APIs and uses the backend-only `FINNHUB_API_KEY`.
