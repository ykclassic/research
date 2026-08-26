# Phase 3.6 — Full Backend Testing and Integration Hardening

## Objective

Establish a repeatable backend acceptance gate covering the complete Phase 3 technical-analysis path, authentication boundaries, API error handling, CORS behavior, deterministic feature calculation, serialization, and production configuration safety.

## Acceptance criteria

Phase 3.6 requires:

1. The complete backend pytest suite passes in CI.
2. Authentication-protected read endpoints reject unauthenticated requests.
3. The health endpoint returns the documented production health contract.
4. CORS behavior is explicitly tested for the configured development origin.
5. Provider and FeatureEngine failures are mapped to controlled HTTP errors.
6. Canonical FeatureEngine inputs and outputs preserve symbol, timeframe, source, candle count, and latest completed candle metadata.
7. Deterministic indicator reference values remain unchanged after performance optimization.
8. Production configuration fails fast when required provider, authentication, CORS, password-reset, or CSRF security settings are missing or unsafe.
9. Frontend CI continues to pass after backend changes.
10. No authentication or Phase 0–2 regression is introduced.

## Performance hardening

The MACD implementation previously recalculated EMA values over every growing prefix of the candle series. It now builds the 12-period and 26-period EMA histories once and derives the MACD series from those histories. This removes the avoidable repeated-prefix calculation while preserving the frozen numerical reference values.

## Security hardening

When `APP_ENV=production`, configuration validation now rejects:

- the development-only CSRF secret;
- CSRF secrets shorter than 32 characters;
- missing non-localhost CORS origins;
- missing Twelve Data credentials;
- missing Supabase URL or publishable key;
- localhost password-reset redirects.

Development and test environments retain their existing defaults.

## Verification

The backend CI workflow runs the complete `python -m pytest -q` suite. The frontend build workflow remains a required regression check because backend contract changes can affect the TypeScript API boundary.

## Phase gate

Phase 3.6 is complete only after the final commit's backend CI and frontend build both pass. Phase 3.7 remains blocked until this gate is satisfied.
