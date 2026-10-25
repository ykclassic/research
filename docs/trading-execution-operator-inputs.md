# Trading execution implementation: operator inputs and release boundaries

This document describes implementation configuration. It is not authorization to enable live orders.

## Required existing application configuration

| Variable | Purpose | Required when |
|---|---|---|
| SUPABASE_URL | Supabase project URL; approved production target is https://rprgjfvfttxydhbekuoc.supabase.co | Backend connects to Supabase |
| SUPABASE_PUBLISHABLE_KEY | Public/publishable key used by the existing application access path | Backend auth/data requests that use the publishable key |
| SUPABASE_SERVICE_ROLE_KEY | Server-only privileged key for execution persistence RPCs | Persistence features run against Supabase; never expose to frontend or logs |
| CSRF_SECRET | Secret used to sign/verify CSRF and execution approval challenges | Backend auth and approval challenge paths |
| CORS_ORIGINS | Allowed frontend origins | Deployed browser clients |
| APP_ENV | Environment profile | All backend environments |

The repository's .env.example also lists market-data, billing/Stripe, OpenAI, SMTP, and GitHub OIDC settings used by other Research app features. They are not all execution-specific. Only configure the integrations actually enabled in the target environment.

## Future exchange-provider inputs — not required for current implementation

No exchange credentials are required by the deterministic simulator. Do not provide production exchange API keys for this implementation phase.

Before any future real-provider integration, the provider-specific setup will need to be defined and tested. At minimum that will include a venue/account identifier, API key, API secret, and any required passphrase or signing material; permissions must be limited to the minimum required and must exclude withdrawals. Store these only in the backend's secret manager. Never put them in frontend variables, repository files, logs, screenshots, or chat messages.

## Operational evidence to collect before production conclusions

- Effective Render deployment SHA and sanitized database project reference.
- Read-only PostgREST probe through the backend's configured path.
- Actual migration ledger and catalog evidence.
- Effective database grants and RPC execute privileges.
- Exact-SHA CI and disposable PostgreSQL integration results.
- Sanitized runtime failure reason codes and health evidence.

Owner-confirmed configuration is not equivalent to an independently observed runtime probe. Do not apply the execution migration to production or deploy this feature merely because code is merged.

## Execution safety defaults

- Live order submission remains disabled in the public API and database RPC boundary.
- The simulator is in-memory, deterministic, and has no network or exchange credentials.
- Unknown submission outcomes require reconciliation; they must not be blindly retried.
- The simulator's in-memory idempotency ledger is not production persistence.
- End-to-end testing is a separate phase after implementation is complete.
- Enabling live submission requires a separate explicit release authorization after all gates pass.
