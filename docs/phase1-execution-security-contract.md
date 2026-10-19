# Phase 1: Migration reconciliation and execution security contract

Status: Phase 1 prototype implemented on a draft branch. No production schema changes, deployment, exchange integration, or orders are authorized.

## Baseline identity

- Repository default branch at review: `main`
- Observed main commit: `4d5eefeb6cd231a7b733db508035fa869814ad7b`
- Render service: `srv-da6bkhgjo6nc73cg1big`, URL `https://research-76vr.onrender.com`
- Supabase project ref: `rprgjfvfttxydhbekuoc`
- Supabase API URL: `https://rprgjfvfttxydhbekuoc.supabase.co`
- A read-only SQL query against that project returned PostgreSQL database `postgres`, schema `public`, and role `postgres`. This verifies the connected Supabase target, **not** the effective connection of the running Render process.

## Migration reconciliation findings

At commit `4d5eefeb6cd231a7b733db508035fa869814ad7b`, the repository tree contains 33 SQL migration files under `supabase/migrations/`. Supabase's recorded migration list contains 29 entries. This count difference alone is not sufficient to decide which migrations are missing: the live ledger contains repeated/renamed Phase 4 research-intelligence entries and multiple ledger names that do not exactly match repository filenames.

### Exact repository migration inventory

1. `20260824233618_watchlists_phase_2.sql`
2. `20260904090000_mtf_candle_cache.sql`
3. `20260906180000_research_history.sql`
4. `20260906190000_alerts_monitoring.sql`
5. `20260906200000_portfolio_decision_support.sql`
6. `20260913200000_settings_foundation.sql`
7. `20260913201000_settings_security_hardening.sql`
8. `20260919200000_signal_outcome_target_tag_audit.sql`
9. `20260921120000_monetization_entitlements.sql`
10. `20260922000000_usage_threshold_notifications.sql`
11. `20260922010000_signal_intelligence_analytics.sql`
12. `20260922044929_signal_intelligence.sql`
13. `20260922090000_phase3_scanner.sql`
14. `20260923000000_phase3_scanner_completion.sql`
15. `20260923150000_phase4_research_intelligence.sql`
16. `20260923193000_phase3_completion_gates.sql`
17. `20260923194500_phase4_completion_gates.sql`
18. `20260923200000_phase5_grounded_copilot.sql`
19. `20260925120000_phase6_quant_lab.sql`
20. `20260925220000_quant_experiment_contract.sql`
21. `20260925233000_phase6_strategy_builder_validation.sql`
22. `20260925240000_phase7_portfolio_intelligence.sql`
23. `20260926003000_phase10_optimization_intelligence.sql`
24. `20260926010000_phase10_model_governance_guardrails.sql`
25. `20260926100000_phase8_research_workspaces.sql`
26. `20260926103000_phase8_research_entitlement.sql`
27. `20260926120000_phase9_infrastructure.sql`
28. `20260926123000_phase9_shared_resource_rls.sql`
29. `20260926124500_phase9_scheduled_exports.sql`
30. `20261002090000_enhanced_signal_entitlement.sql`
31. `20261006090000_billing_paid_plan_lifecycle.sql`
32. `20261007190000_fix_consume_usage_period_start_ambiguity.sql`
33. `20261007211000_fix_consume_api_usage_period_start_ambiguity.sql`

### Schema evidence and stop conditions

A read-only inventory of the live `public` schema did not find these tables:

- `mtf_candle_cache`
- `quant_experiments`
- `paper_portfolios`
- `paper_trades`
- `strategy_definitions`

The schema does contain workspace tables even though repository migration names and live migration names do not line up exactly. Therefore, do not replay migrations based only on filenames, and do not mark a migration as unapplied solely because a table is absent. For every migration, compare:
1. filename timestamp/name and SQL checksum;
2. exact live `supabase_migrations.schema_migrations` version/name row;
3. objects and policies expected from that SQL against `pg_catalog` / `information_schema`;
4. subsequent migrations that may have renamed, replaced, or superseded the objects;
5. data-preservation and rollback implications.

Do not apply, repair, squash, delete, or mark migrations applied in production during this phase. Produce a reviewed reconciliation matrix first, with states `MATCHED`, `SCHEMA_PRESENT_LEDGER_MISMATCH`, `LEDGER_PRESENT_SCHEMA_MISSING`, `NOT_APPLIED`, `SUPERSEDED`, or `UNRESOLVED`. The current evidence establishes drift but does not yet provide a complete row-by-row final classification.

## Safe deployed database diagnostic

Add a small backend diagnostic only after its access model is reviewed. It must derive its target from the running process's effective settings, not from a separately supplied expected URL. Response fields should be limited to:

- `configured`: boolean;
- `project_ref`: validated hostname-derived Supabase project ref, or null;
- `database_probe`: `ok`, `failed`, or `not_configured`;
- `probe_kind`: fixed label for a non-mutating probe;
- `deployment_commit`: existing Render commit identifier, when available.

Never return the URL path/query, credentials, API keys, authorization headers, connection strings, database server address, raw exception text, or SQL results containing user data. Do not expose an unrestricted unauthenticated diagnostics endpoint; prefer a protected operator-only check (e.g. the existing trusted GitHub Actions OIDC verifier pattern) and a fixed allow-listed read-only probe. A passing result must be recorded from the deployed Render response before claiming that Render's effective DB target is confirmed.

## Execution security contract (required before enabling execution)

### Request boundary

- Authenticate using the existing `mr_access_token` cookie and `get_current_user`.
- Require `_require_csrf` for state-changing cookie-authenticated requests; reject missing/mismatched token and invalid production Origin.
- Resolve entitlement server-side from the authenticated user's current subscription and feature rows. The client cannot submit a plan name or entitlement assertion.
- `live_trade_execution` is a new server-defined feature key. Until a reviewed migration explicitly grants it to Premium and verification confirms the live rows, all requests must be denied. Pro and Free must remain denied. Do not infer Premium eligibility from frontend state or the existing `enhanced_signal` entitlement.
- Client fields `approved`, `approval_id`, `approved_at`, and `expires_at` are not evidence of approval and must not authorize execution. Remove them from the public request schema. An approval must be created and stored server-side, owned by the authenticated user, bound to a single immutable proposal and its risk/market snapshot, and consumed atomically once.
- Until persistence and revalidation exist, the endpoint must fail closed with no adapter invocation, even for Premium users.

### Revalidation sequence

Immediately before a future broker boundary, require all checks to succeed:

1. approval exists, is pending, belongs to the caller, is unexpired, matches the proposal hash, and has not been consumed or revoked;
2. proposal remains `QUALIFIED`; risk-policy version is current; risk limits still pass;
3. fresh exchange account/balance/positions/open orders are available and within a configured age bound; do not use client-supplied equity;
4. market quote/candles are from verified providers, complete where required, and fresh; spread/slippage guardrails pass;
5. current portfolio/correlation and daily drawdown constraints pass;
6. Premium entitlement is active at request time and live execution remains globally disabled unless separately enabled through an explicit, audited operational gate;
7. atomically consume approval and create a unique execution-intent/idempotency record before any adapter call.

Any missing value, timeout, stale snapshot, provider error, database error, duplicate request, version mismatch, unknown status, or ambiguous broker outcome must block new submissions. A broker timeout after a request may have reached the venue must enter an `UNKNOWN_RECONCILIATION_REQUIRED` state and must not be blindly retried.

## Proposed durable record design (not yet a migration)

Use append-only records with database-enforced immutability and a separate append-only event stream:

- `execution_approvals`: id, user_id, proposal_id, proposal_hash, risk_policy_version, account_snapshot_hash, market_snapshot_hash, approved_at, expires_at, status, consumed_at, revoked_at, created_at. Creation is server-owned; the UI can approve only through a narrow server command that validates ownership and CSRF. Do not allow direct client INSERT/UPDATE/DELETE.
- `execution_intents`: id, user_id, approval_id, idempotency_key (unique per user), proposal_hash, validated snapshot references/hashes, immutable order parameters, state, created_at.
- `execution_events`: id, intent_id, event_type, reason_code, safe metadata, occurred_at, previous_event_hash/event_hash if hash chaining is adopted. No credential-bearing or raw provider exception fields.
- If order status requires mutable current state, keep it as a rebuildable projection updated only by a trusted service role; the append-only event stream remains the audit source of truth.

Database requirements: RLS enabled; no direct `anon`/authenticated writes; owner-scoped reads only where necessary; service-role writes limited to backend; explicit grants; CHECK constraints for state transitions; unique idempotency key; foreign keys; UTC timestamps; triggers that reject UPDATE/DELETE on immutable evidence tables. Revocation/consumption must be represented as new events or narrowly controlled status transitions with immutable event evidence, not by rewriting the approval history.

## Test contract before any adapter integration

- anonymous caller -> 401; authenticated cookie without CSRF -> 403; invalid Origin -> 403;
- Free and Pro -> 403; Premium without explicit live feature row -> 403; entitlement lookup outage -> 503/deny;
- forged approval payload, foreign user's approval, expired/revoked/consumed approval, changed proposal hash -> deny;
- stale/missing account snapshot, market snapshot, or portfolio state -> deny;
- risk service/provider/database timeout -> deny and no adapter invocation;
- concurrent duplicate idempotency key -> at most one intent/consumption;
- UPDATE/DELETE against append-only approvals/events -> database rejection;
- adapter is not called until all revalidation gates pass; no live adapter is included in this phase;
- ambiguous broker response enters reconciliation state and is not retried automatically.

## Phase 1 work order

1. Complete and review the migration reconciliation matrix. Do not apply migrations.
2. Implement a protected, sanitized effective-DB diagnostic and verify it against the deployed Render response without changing production configuration.
3. Harden the execution HTTP boundary (authentication, CSRF, Premium entitlement) and make it explicitly fail closed while no server-side approval store exists.
4. Remove client-controlled approval assertions from the public request model.
5. Add API/security tests and repository-contract tests; use a local/test database for immutability constraints once the migration design is reviewed.
6. Only after the matrix is signed off, draft (but do not apply) the new migration for approval/intent/event persistence. Review RLS, grants, triggers, idempotency and rollback behavior.
7. Prove fail-closed account/risk/market-state revalidation using injected failures and assert zero adapter calls.

## Explicit exclusions

No production SQL/DDL, migration ledger repair, Render/Vercel deployment, exchange adapter, live trading enablement, or order submission is included. CI green alone is not production acceptance.


## Phase 1 prototype: persisted intent, approval, and event contract

Migration source: `supabase/migrations/20261019120000_execution_approval_intent_audit.sql`. This file is present only in the feature branch and has been exercised against a disposable PostgreSQL 16 service in GitHub Actions. It has **not** been applied to Supabase production.

### Persistence model

- `execution_intents`: immutable proposal inputs and their signal/account/market/risk snapshots; mutable lifecycle state; unique per-user idempotency key; canonical request hash.
- `execution_approvals`: one immutable decision per intent, actor/user ownership, expiry, approval snapshot and snapshot hash. Approval JSON must carry the same request hash as the intent.
- `execution_records`: immutable terminal outcome, unique per intent and approval, and idempotency key bound to the original intent.
- `execution_events`: append-only audit stream. Update/delete triggers reject mutation.
- The intent lifecycle is constrained to `AWAITING_APPROVAL → APPROVED|REJECTED → EXECUTING → EXECUTED|FAILED|UNKNOWN`. The database RPCs enforce ownership, expiry, rejection isolation, and one-time claim. An `UNKNOWN` result is not automatically retryable; it requires a separate reconciliation process.

### Database access boundary

RLS is enabled on all four tables, with no browser-role policies. Direct table grants are revoked for `anon`, `authenticated`, and `service_role`; only the narrowly scoped service-role RPCs are granted execution. The RPCs use `SECURITY DEFINER` with a fixed search path. The migration assumes the Supabase migration owner owns the objects, as it does in the intended deployment model; the disposable PostgreSQL workflow verifies SQL behavior and browser-role privilege denial.

### Atomic operations

1. `create_execution_intent` creates the intent and its first audit event atomically. Repeating the same user/idempotency key and request hash returns the original intent without another event. Reusing that key with a different hash fails.
2. `record_execution_approval` locks the intent, checks ownership/status/expiry, binds the immutable approval snapshot to the intent request hash, writes the decision, transitions intent status, and appends an event in one transaction. A rejected intent cannot be claimed.
3. `claim_execution` atomically moves an approved intent to `EXECUTING` only when the approval is valid and a matching successful revalidation proof is no more than 15 seconds old. It binds account reference, symbol, request hash, and risk-policy version. A duplicate claim fails.
4. `record_execution_result` writes a single immutable result and audit event and transitions the intent to a terminal state. It permits recording a result after the approval expiry if the order was already claimed; this avoids losing reconciliation evidence due to a slow broker response. It requires the original idempotency key. A transport timeout must be recorded as `UNKNOWN`, never retried automatically.

### Fresh-state revalidation prototype

`backend/app/services/execution_revalidation.py` implements a deterministic validation contract with injected account, market, and risk providers. Missing providers, provider exceptions, missing/malformed timestamps, stale data, clock skew, wrong account/symbol, non-tradable market, price drift, invalid stop/target structure, reward-to-risk below 2R, daily loss at/above 2%, two or more correlated positions, disabled execution, a risk policy mismatch, risk above 0.75%, or a recalculated size differing from the approved size all reject the request.

Freshness limits: market 15 seconds; account and risk 30 seconds. Maximum entry drift is 0.25%. A successful proof is explicitly marked `passed=true`, includes a timestamp and snapshot bindings, and is required by the database claim RPC. These values are code defaults for the contract and require product/risk-owner review before any live feature is enabled.

The provider protocols are deliberately injected and **no live exchange provider is implemented or wired**. The public execution route still returns a fail-closed 503 even if entitlement succeeds; the new persistence/revalidation code is not reachable from an order-submission route.

### CI evidence

- Backend CI: 552 passed, 1 skipped at the last completed code-bearing run; the skip is the PostgreSQL integration module in the generic runner because it has no disposable database configured.
- Dedicated PostgreSQL 16 integration workflow: 7 passed at the last completed run. It applies the branch migration to a throwaway database and tests idempotency, payload mismatch, immutable approvals/records/events, rejected proposal isolation, single-use claims, and browser-role denial.
- Revalidation tests are included in backend CI and exercise stale/missing snapshots, provider errors, disabled execution, account/risk limits, price drift, policy mismatch, and size changes.

The latest edits that tightened claim-time revalidation and quantity matching are awaiting their own CI completion; do not infer their checks from earlier runs.

## Phase 1 exit conditions

Before the PR can be considered for merge:
1. The newest commit must pass Backend CI, Frontend build, Branch Governance, and PostgreSQL integration.
2. A reviewer must inspect the SQL migration and security model, including the role/ownership behavior on Supabase.
3. The migration matrix must retain the three unresolved ledger-only records as explicit history gaps; do not fabricate matching source files or mark them repaired.
4. The protected database diagnostic must be deployed and observed before asserting the Render process uses the intended project. That deployment is not part of this prototype.
5. The execution route must remain disabled until real authenticated approval endpoints, current entitlement rows, provider adapters for read-only account/market state, and end-to-end failure injection are reviewed.
