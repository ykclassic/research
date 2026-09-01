# Phase 5.3 — Regime Evidence / Threshold Validation

## Contract

The regime engine is deterministic and consumes only completed canonical candles. Every result contains:

- `regime`: one of the seven canonical labels.
- `confidence`: bounded to `[0, 1]` and derived from deterministic evidence only.
- `evidence`: the numerical and structural inputs used by the rules.
- `thresholds`: the exact thresholds used for that result.
- `rule_id` and `rule`: the rule that produced the classification.
- `source`, `provider_timestamp`, and `latest_candle_timestamp`: provenance.

## Thresholds

| Input | Boundary |
|---|---:|
| ADX strong | 25.0 |
| Trend persistence strong | 0.70 |
| Trend persistence weak | 0.50 |
| Directional ratio strong | 0.55 |
| Directional ratio weak | 0.25 |
| High volatility percentile | 0.80 |
| Low volatility percentile | 0.20 |

Boundaries are explicit and inclusive where the rule uses `>=` or `<=`. Range requires directional ratio `< 0.25`.

## Rule precedence

1. Missing/non-finite required indicators → `UNKNOWN`.
2. Direction/EMA conflict → `UNKNOWN`.
3. Strong trend up/down.
4. High volatility.
5. Low volatility.
6. Weak trend.
7. Range.
8. Otherwise → `UNKNOWN`.

This precedence is part of the contract and prevents overlapping conditions from producing non-reproducible labels.

## API

Authenticated endpoint:

`GET /api/regime/{symbol}?timeframe=1h&limit=250`

Minimum history is 220 completed candles. Forming candles are rejected by the regime engine and cannot enter classification.

## Production verification

`backend/scripts/verify_production_regime.py` verifies:

1. unauthenticated requests are rejected;
2. the deployed API is reachable with trusted GitHub OIDC;
3. the requested symbol/timeframe are returned;
4. the result source is `twelve_data`;
5. provider data is fresh relative to the timeframe plus a 180-second publication tolerance;
6. the regime label, confidence, evidence, rule, and thresholds satisfy the production contract.

The production workflow uses short-lived GitHub OIDC credentials and does not use a static user-session secret.
