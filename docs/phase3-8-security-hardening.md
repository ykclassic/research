# Phase 3.8 — Security Hardening

## Objective

Harden the deployed technical-analysis application without changing the Phase 0 authentication architecture or the deterministic Phase 3 research model.

## Implemented controls

### Backend

- Production configuration rejects the default CSRF secret.
- Production configuration requires non-local CORS origins.
- Production configuration requires Twelve Data and Supabase configuration.
- Production password-reset redirects cannot target localhost.
- Trusted Host validation is enabled.
- The current Render host is included in the secure default trusted-host set; custom production domains should explicitly set `TRUSTED_HOSTS`.
- CSRF-protected state-changing routes validate the request Origin against configured CORS origins in production.
- CSRF still requires the existing signed-token/double-submit validation.
- API responses use `Cache-Control: no-store` to prevent browser/proxy caching of authenticated or market-sensitive responses.
- Security response headers are emitted by FastAPI:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`
  - `X-Permitted-Cross-Domain-Policies: none`
  - `Strict-Transport-Security` in production

### Frontend

Vercel response headers now include:

- HSTS
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy
- Permissions-Policy
- Content-Security-Policy with the production API as the permitted `connect-src`
- `frame-ancestors 'none'`
- `base-uri 'self'`
- `form-action 'self'`

## Security decisions

### No in-memory rate limiter

A process-local rate limiter was intentionally not added. It would not provide reliable protection across multiple Render instances and would create inconsistent behavior after restarts. Distributed rate limiting should be implemented with a shared store when required by the production threat model.

### Authentication architecture unchanged

The existing Supabase session-cookie model, password recovery, logout flow, and CSRF mechanism remain intact. This phase adds defense-in-depth around that architecture rather than replacing it.

## Acceptance criteria

- [ ] Backend CI passes on the final security commit.
- [ ] Frontend build passes on the final security commit.
- [ ] Security-header tests pass.
- [ ] Trusted-host rejection test passes.
- [ ] Production CSRF origin rejection/acceptance tests pass.
- [ ] Existing authentication tests remain green.
- [ ] Production Render deployment succeeds.
- [ ] Production API returns security headers.
- [ ] Production Vercel deployment returns security headers and CSP.
- [ ] Authenticated logout/watchlist mutation continues to work with the legitimate frontend origin.
- [ ] No authentication regression is observed.

## Certification rule

Phase 3.8 is not complete from CI alone. Production header verification and authenticated CSRF regression testing must pass before Phase 3.9 begins.
