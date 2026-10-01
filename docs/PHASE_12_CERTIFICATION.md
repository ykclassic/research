# Phase 12 — System Validation & Certification

## Objective

Phase 12 proves that the implemented trading-research pipeline is internally consistent, deterministic, fail-closed, and protected against temporal leakage before operational hardening in Phase 13.

This phase does **not** add new trading intelligence. It converts the safety and integrity requirements accumulated through Phases 1–11 into permanent regression gates.

## Certification matrix

| Domain | Required evidence | Gate |
|---|---|---|
| Market data | Strict candle ordering, identity, finite OHLCV, completed-candle separation | PASS |
| Feature / regime inputs | Completed data only; deterministic inputs | PASS |
| SMC / market structure | Causal event inputs; no future source candles | PASS |
| MTF | Ordered Daily → H4 → H1 → M15 hierarchy and deterministic qualification | PASS |
| Strategy portfolio | Registered strategies remain evaluable without hidden selection | PASS |
| Strategy selection | MTF gate cannot be bypassed by a conflicting strategy | PASS |
| Risk | Invalid equity/ATR/size cannot produce a qualified position | PASS |
| Execution | Only risk-qualified, authorized orders may reach an adapter | PASS |
| Execution safety | Research-only and unsupported LIVE modes fail closed | PASS |
| Trade lifecycle | FILLED → OPEN → CLOSED transition is enforced; closed trades cannot close twice | PASS |
| P&L | Realized P&L and R are directionally consistent | PASS |
| Performance | Open trades excluded; summary is deterministic | PASS |
| Determinism | Repeated equivalent inputs produce equivalent canonical results | PASS |
| API/security | Existing CI/API/auth/OIDC gates remain mandatory | CI |
| Production provenance | Deployed API identifies the serving Render commit | CI / production verifier |
| Production market data | Independent provider and freshness verification remains mandatory | Production verifier |
| Research isolation | AI research artifacts remain outside the canonical production dependency path | CI / code review |

## Adversarial cases covered in Phase 12

- Duplicate candle timestamps.
- Mixed symbol/source/timeframe candle identity.
- Forming candles separated from completed candles.
- Non-finite account equity.
- Non-finite OHLCV values.
- Invalid risk direction and risk controls.
- Unqualified position crossing the execution boundary.
- Missing/invalid human authorization.
- Expired authorization.
- Research-only execution.
- LIVE execution without a live-capable adapter.
- Double-closing a trade.
- Invalid order quantity.
- Invalid filled quantity.
- P&L/R consistency.
- Open-trade exclusion from performance statistics.

## End-to-end certification path

The primary integration test follows the implemented control chain:

`qualified strategy → risk qualification → order construction → explicit authorization → paper execution → OPEN trade → CLOSED trade → performance summary`

A failure at any safety boundary must stop progression rather than silently manufacture a downstream result.

## Temporal-leakage rule

All decision-time calculations must use information available at or before the decision timestamp. Current snapshot status from the SMC layer must not be treated as historical truth in backtests; historical state must be recomputed causally for each decision point.

## Release rule

Phase 12 is complete only when:

1. The full backend test suite is green.
2. The Phase 12 certification suite is green.
3. Frontend build/tests are green.
4. Branch Governance is green.
5. Vercel/deployment checks are green where applicable.
6. No live broker adapter is introduced as part of certification.
7. Production market-data verification remains green with deployment provenance matching the intended Render commit.
8. The Phase 12 PR is merged through the governed branch process; no direct `main` commit is permitted.
