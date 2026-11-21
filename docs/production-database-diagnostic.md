# Production database diagnostic contract

The `GET /internal/diagnostics/database` endpoint is restricted to trusted GitHub Actions OIDC identities. The OIDC token authenticates the workflow caller; it is not sent to Supabase and is not treated as a Supabase user JWT.

The backend independently uses its configured Supabase service-role credential for one fixed read-only PostgREST request:

```http
GET /rest/v1/billing_plans?select=id&limit=1
```

The query returns at most one plan identifier and does not mutate database state. The endpoint does not return the row or any credential-bearing material.

## Required backend environment

Configure `SUPABASE_EXPECTED_PRODUCTION_PROJECT_REF` to the exact project ref for the intended production Supabase project. It must be the 20-character project ref, not a URL.

The diagnostic fails closed and performs no database request if any of these conditions is true:

- expected project ref is missing or malformed;
- configured Supabase URL is not a canonical HTTPS `<project-ref>.supabase.co` URL;
- URL project ref does not exactly match the expected project ref;
- `RENDER_GIT_COMMIT` is missing or is not a 40-character hexadecimal commit SHA;
- the backend service-role credential is not configured.

The endpoint reports fixed reason codes only. It never returns the Supabase URL, service-role key, HTTP headers, response rows, or raw exception text.

## Interpretation

A `passed` result confirms that the protected workflow reached the expected configured Supabase project and that the fixed read-only PostgREST query returned a JSON array. It does not certify general database health, schema completeness, RLS behavior for end users, or application write paths.

A `failed` result is not a reason to bypass the gate. Investigate the fixed reason code and configuration before retrying.

No production configuration is changed by this documentation or by the diagnostic code change itself.
