# Trading execution implementation status and roadmap

## Non-negotiable boundary

Live order submission remains disabled until a separate, explicit release authorization. A signal is not an order authorization. Client-side approval fields are never trusted.

## Delivery sequence

1. Merged baseline: verify exact-SHA CI and keep the execution API fail-closed.
2. Authorization: enforce authenticated ownership, CSRF, server-side Premium entitlement and database privilege boundaries.
3. Persistence: validate the execution migration against disposable PostgreSQL; preserve one-time approval, immutable snapshots, append-only events and idempotency.
4. Approval lifecycle: bind a short-lived, single-use challenge and approval to the exact intent hash.
5. Risk revalidation: require fresh account, market and risk snapshots; block on missing/stale data, policy mismatch, exposure breaches or changed approved quantity.
6. Orchestration: persist intent before any provider boundary; handle retries idempotently; classify ambiguous outcomes as unknown and require reconciliation.
7. Simulation: test acceptance, rejection, partial fill, full fill, pre-submit timeout, post-submit timeout and provider outage without any network adapter.
8. Observability/recovery: expose sanitized reason codes, audit trails, stuck-intent detection, reconciliation and operator runbooks.
9. Production readiness: independently observe deployment/database identity, read-only data access, migration state, effective grants and exact-SHA test results.
10. Controlled release: only after all prior gates and separate explicit authorization may a narrow allowlisted live-execution rollout be considered.

## Current implementation status at roadmap start

- PR #252 is merged to main at 83d8625641bd4d9bd0b0ae9a0ee4bcb0df2d2b23.
- Backend CI, frontend build, branch governance, PostgreSQL execution persistence integration and production portfolio E2E workflow passed on that merge commit.
- Production Market Data Verification failed on the merge commit (run 40212276028, repeated later as 40232539324); this is a separate production market-data gate and must be diagnosed rather than represented as green.
- POST /api/execution/order remains fail-closed.
- SQL claim_execution and record_execution_result remain hard-stopped.
- The proposed execution migration must not be applied to production during implementation.
- Production runtime database identity has not been independently observed in this implementation status.
- End-to-end feature testing has not started.

## Simulator contract

The deterministic simulator must never use real network calls or exchange credentials. It should prove:
- no submission without valid approval and successful risk revalidation;
- non-simulation modes are blocked;
- idempotency keys cannot be reused for a changed order;
- ambiguous outcomes are not automatically resubmitted;
- provider lookup reconciles a possibly accepted order;
- partial fills are represented explicitly;
- provider outages fail closed.
