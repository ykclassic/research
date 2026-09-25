# Phase 4 / Phase 5 Production Deployment Certification

## Certified baseline

The production application baseline is the current `main` revision. Phase 4 Research Intelligence and Phase 5 Grounded Research Copilot are both present in the repository.

### Phase 4

- Persistent research snapshots and timeline
- What Changed comparisons: previous session, previous report, previous day, previous week, and saved snapshot
- Research watchpoints and transition events
- Catalyst/event intelligence
- Claim-to-evidence provenance including source, timestamp, method, and engine/model version
- Production verification and completion gates

### Phase 5

- Grounded Research Copilot
- Evidence-first research runs
- Persistent run state and history
- Tiered Pro/Premium entitlements
- Scheduled grounded research
- Explicit evidence citation contract
- Production deployment and backend verification

## Deployment rule

Frontend production must serve the same certified `main` revision as the backend. Preview deployments may be used for validation, but a phase is not considered live until the production aliases point to the certified revision.

## Verification

After a production deployment, verify:

1. Vercel production revision matches `main`.
2. Render live deployment matches `main`.
3. Phase 4 research-intelligence endpoints are reachable for an authenticated user.
4. Phase 5 grounded-copilot endpoints enforce entitlements and return only verified evidence.
5. Supabase Phase 4/5 tables and RLS policies are present.
6. Existing billing, authentication, scanner, signal intelligence, and market-data verification remain green.
