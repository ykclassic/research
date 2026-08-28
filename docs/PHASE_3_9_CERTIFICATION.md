# Phase 3.9 — Production Market-Data Verification Certification

## Objective

Prove that the deployed Research API is the authoritative path for live market data and that returned prices are sourced, fresh, independently corroborated, and not stale cached frontend data.

## Acceptance criteria

| Criterion | Required evidence | Status |
|---|---|---|
| API reachable | Direct request to Render `/health` returns HTTP 200 and healthy payload | PASS — existing production verifier run |
| API obtains data from Twelve Data | API payload and `X-Market-Data-Source` identify `twelve_data`; direct Twelve Data comparison succeeds | PASS — existing production verifier run |
| Data timestamp is fresh | Provider timestamp and backend `observed_at` remain within configured age budgets | PASS — existing production verifier run |
| Current quote distinct from latest completed candle | Live quote timestamp/price is distinguishable from latest completed analysis candle | PASS — existing production verifier run |
| Independent price agreement | CoinGecko BTC/USD price is within 0.50% of API quote and independent timestamp is fresh | PASS — existing production verifier run |
| No stale application cache | Forced refreshes report `MISS`, responses are `no-store`, and backend observation timestamp advances | PASS — existing production verifier run |
| Frontend is not responsible | Verifier calls Render API directly and never calls the Vercel frontend | PASS — existing production verifier run |
| Production authentication is non-user-bound | GitHub Actions uses a short-lived GitHub OIDC JWT instead of a copied Supabase user session | IMPLEMENTED; final production run required |
| OIDC trust is restricted | Backend validates issuer, audience, repository, main ref, exact workflow, and approved workflow events | IMPLEMENTED; unit tests added |
| Verification is automated | Workflow supports manual execution and runs every six hours | IMPLEMENTED |

## Verification tolerances

- Direct Twelve Data comparison: **0.10%** maximum relative error.
- Independent CoinGecko comparison: **0.50%** maximum relative error.
- Provider quote age: **120 seconds** maximum.
- Backend observation age: **15 seconds** maximum.
- Independent CoinGecko timestamp age: **60 seconds** maximum.

## Authentication architecture

The production verifier no longer uses `MR_ACCESS_TOKEN`.

GitHub Actions requests a short-lived OIDC JWT with audience `research-production-verifier`. The backend verifies the JWT against GitHub's OIDC issuer/JWKS and requires all of the following:

- repository: `ykclassic/research`
- ref: `refs/heads/main`
- workflow: `.github/workflows/production-market-data-verification.yml`
- event: `schedule` or `workflow_dispatch`
- valid `iss`, `aud`, `exp`, `iat`, and signature

The OIDC path is available only through the market/analysis read-router dependency. It does not grant access to authentication, watchlist mutation, or administrative endpoints.

## Final certification gate

Phase 3.9 is **PASS** only after the following final production sequence completes successfully:

1. Render deploys the `main` branch containing the OIDC implementation.
2. Run **Production Market Data Verification** manually.
3. The workflow prints:

   `CERTIFIED: deployed market-data verification passed.`

4. Confirm the run used the OIDC authentication path and not `MR_ACCESS_TOKEN`.
5. Delete the obsolete GitHub Actions `MR_ACCESS_TOKEN` secret.
6. Retain `TWELVE_DATA_API_KEY` as the only secret required by this verification workflow.

The previous green run remains valid evidence for the market-data assertions, but it does not by itself certify the new OIDC authentication path. The final OIDC-backed green run is the release gate.
