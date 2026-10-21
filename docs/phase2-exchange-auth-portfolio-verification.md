# Phase 2 — Exchange Authentication and Portfolio Verification

**Status:** implementation branch opened from Phase 1 security-contract head `3cf8cea4ed58863ea80a4088df3f4a9267539ac4`. This is a read-only phase. No production deployment, credential changes, migrations, exchange writes, or orders are authorized.

## Objective

Prove that the backend can authenticate to the intended XT.com account and retrieve a fresh, structurally valid portfolio snapshot without exposing secrets or enabling trading. This phase supplies authoritative account state for later risk revalidation; it does not authorize execution.

## Scope

1. Implement a dedicated XT Spot read-only client with a fixed production origin and allow-listed GET endpoints only.
2. Use XT's documented request-signing headers and millisecond timestamp; keep API key and secret server-side. Never accept a caller-supplied base URL, signing algorithm, path, or arbitrary query parameters.
3. Require a credential configured specifically for read-only account/balance access. Trading and withdrawal permissions must not be required or used. Do not log keys, signatures, headers, raw provider bodies, or exception text.
4. Parse amounts as decimal values, reject malformed/non-finite/negative balance fields, and preserve available, frozen, and total amounts without inventing missing values.
5. Return normalized account/portfolio state with `observed_at`, provider identity, account-reference fingerprint, freshness, and sanitized status/reason code. Portfolio amounts are owner-authorized data, not public diagnostics.
6. Use bounded connection/read timeouts, conservative rate limiting, and no retry for authentication, authorization, schema, or other non-transient failures. Never silently return cached data as fresh.
7. Keep exchange reads independent from order submission. The client exposes no order-placement, transfer, withdrawal, or other mutating method.

## Initial endpoint contract

- Origin: `https://sapi.xt.com` (fixed in code).
- Read-only spot balance endpoint: `GET /spot/v4/balances`.
- Authentication headers follow XT's official Spot API signing instructions: `validate-appkey`, `validate-timestamp`, `validate-signature`, `validate-recvwindow`, and `validate-algorithms`.
- Official references:
  - https://doc.xt.com/docs/margin-spot/Access%20Description/BasicInformationOfTheInterface
  - https://doc.xt.com/docs/margin-spot/Access%20Description/signatureInstructions
  - https://doc.xt.com/docs/margin-spot/Access%20Description/signature-generation
  - https://doc.xt.com/docs/trading-third-party/Balance/GetListOfCurrencyAssets

The initial client and deterministic local HMAC vector are now present in `backend/app/services/xt_readonly.py` and `backend/tests/test_xt_readonly.py`. The vector proves deterministic implementation behavior, not exchange interoperability. XT's current documentation shows `validate-*` headers while its legacy request demo uses `xt-validate-*`; verify the current signature preimage/header contract against an official current SDK or XT testnet before enabling a live request. Do not treat a locally self-consistent HMAC test as proof of authenticated access.

## Security and data contract

- Secrets are read only from server-side configuration; no secrets in frontend bundles, URLs, API responses, telemetry, or test fixtures.
- API credentials must have read-only account/balance scope. If the account cannot be verified as read-only, the phase fails closed.
- Do not accept client-supplied equity, balances, positions, account IDs, freshness timestamps, or exchange identity as authoritative.
- Every snapshot is tagged with the provider, normalized account fingerprint, server observation time, and validation result.
- Provider errors map to fixed reason codes such as `credentials_missing`, `authentication_failed`, `permission_denied`, `rate_limited`, `provider_unavailable`, `invalid_response`, and `stale_snapshot`. Raw provider text is not returned.
- No production secrets are to be added to GitHub, PR comments, CI logs, or this document.

## Required automated tests

- Correct HMAC/signature preimage and headers using official, fixed test vectors; timestamp and receive-window behavior.
- Missing credentials, malformed configuration, invalid timestamp, bad signature response, permission denial, rate limiting, timeout, malformed JSON, provider error envelope, and unexpected response shape all fail closed.
- HTTPS origin and path are fixed; redirects to a different host are rejected; no arbitrary URL injection.
- Balance parsing uses decimal arithmetic and rejects NaN/infinity, negatives, and inconsistent totals; empty assets are represented honestly.
- Sanitized diagnostics contain no API key, secret, signature, authorization header, raw body, or raw exception.
- Freshness is computed server-side; missing, stale, or future-dated provider data is not labelled fresh.
- Test asserts every request is GET to an allow-listed read endpoint and no order/transfer/withdrawal request can be made.
- Entitlement/ownership checks prevent one user from reading another user's account snapshot.
- Provider outage and missing account state cause the downstream execution revalidation to block; no broker adapter is invoked.

## Manual acceptance gate

1. Confirm the XT API key has read-only account/balance permissions and no trade or withdrawal permissions.
2. Confirm the target account identity through a trusted operator process without exposing the account's full identifiers.
3. Run one bounded authenticated balance request against XT using the approved credential; retain only timestamp, sanitized result, normalized account fingerprint, and response reason/status.
4. Compare the normalized snapshot against the XT account UI independently. Do not record raw balances in CI artifacts or public logs.
5. Confirm the running backend commit and effective credential configuration source before any deployed test. A local test or CI result does not establish production connectivity.
6. Verify no order submission, transfer, withdrawal, or live execution path is available from this phase.

## Exit gate

Phase 2 is complete only when automated tests pass and a controlled, read-only authenticated request returns a valid fresh snapshot from the intended XT account with sanitized evidence. CI alone is insufficient. Until then, downstream execution remains disabled and fail-closed.

## Explicit exclusions

No live orders, paper/live broker adapter, withdrawal/transfer calls, production credential changes, production deployment, database migration, entitlement grant, or execution enablement. Those require separate review and explicit authorization.
