# Bug Reports & Production Defect Management Standard

**Repository:** `ykclassic/research`  
**Scope:** Full lifecycle — development, QA, CI/CD, security, data integrity, deployment, production operations, regressions, and release governance  
**Status:** Version 1.0 — Draft for review  
**Primary production baseline:** `main`

## 1. Purpose

This document defines the canonical process for reporting, triaging, reproducing, diagnosing, fixing, verifying, and closing defects in the market-intelligence platform.

The standard is tailored to the platform's production concerns:

- live market-data ingestion and provider provenance
- quantitative analytics, indicators, scoring, and signal generation
- risk and alert logic
- database persistence and recovery
- external APIs, webhooks, and notifications
- authentication, authorization, secrets, and configuration
- backend/frontend/API contracts
- scheduled and background jobs
- CI/CD and branch/phase governance
- cloud deployment and runtime behavior
- AI-assisted research and grounded intelligence
- production verification and auditability

A defect is treated as a lifecycle event, not simply a GitHub issue.

## 2. Governing principle

A defect is not considered fixed merely because the visible symptom disappears or one test passes.

For production-impacting defects, the default evidence chain is:

**Detect → Record → Reproduce → Classify → Diagnose → Identify root cause → Fix → Add regression protection → Run relevant tests → Run complete required CI gates → Verify deployed revision where applicable → Record evidence → Close**

If the defect cannot be reproduced, the report must document what was attempted, the available evidence, the uncertainty, and the monitoring or diagnostic action taken.

## 3. Relationship to phase and branch governance

The repository's phase-gate policy states that `main` is the production baseline, phase work must be isolated from `main`, and phase changes enter `main` through a PR only after all acceptance gates pass.

Bug fixes therefore follow:

- **Production defect on main:** `hotfix-<description>`
- **Defect discovered during a phase:** fix on that phase branch when it belongs to that phase
- **Documentation/process-only change:** dedicated documentation branch is preferred
- Never commit application defect fixes directly to `main`
- Merge only through PR after required tests and verification are green
- A passing feature branch is not evidence that `main` contains the fix

## 4. Defect taxonomy

Every report must have at least one primary defect class.

### 4.1 Application defects
Incorrect behavior in backend, frontend, services, domain logic, APIs, or workflows.

### 4.2 Regression defects
Behavior that previously worked and became incorrect after a change.

### 4.3 Market-data integrity defects
Wrong, stale, missing, duplicated, mis-timestamped, mis-symbolized, or incorrectly attributed market data.

Examples:

- stale quote presented as live
- wrong provider shown beside a quote
- provider timestamp replaced by server/request timestamp
- unsupported symbol silently mapped to another instrument
- timeframe gaps not detected
- fallback provider used without satisfying the routing contract

### 4.4 Quantitative/analytics defects
Incorrect indicator, feature, scoring, statistical, regime, signal, or research calculation.

Reports must identify relevant inputs, timeframe, parameters/configuration, expected mathematical behavior, actual result, and numerical edge cases.

### 4.5 Risk/alert defects
Incorrect risk calculations, alert thresholds, signal suppression, alert flooding, notification deduplication, or safety guardrails.

The platform must remain an intelligence/alerting system unless an explicitly approved architecture says otherwise; unexpected trade-execution hooks are security/safety defects.

### 4.6 Database/state defects
Persistence, schema, migration, transaction, concurrency, indexing, connection, cache, restart-recovery, or state-consistency failures.

### 4.7 Integration/API/webhook defects
Failures involving external providers, authentication contracts, REST APIs, WebSockets, webhooks, Discord/notification integrations, rate limits, retries, timeouts, or payload contracts.

### 4.8 Security/configuration defects
Secrets exposure, broken authentication/authorization, RBAC failure, unsafe input handling, injection risk, insecure configuration, client-side credential exposure, or environment drift.

### 4.9 Frontend/UI defects
Incorrect rendering, navigation, state handling, responsive behavior, stale UI state, accessibility, chart behavior, or frontend/backend contract mismatch.

### 4.10 Scheduler/background-worker defects
Missed jobs, duplicate jobs, stuck workers, incorrect schedules, overlapping executions, retry storms, or jobs that silently stop.

### 4.11 CI/CD/workflow defects
Broken tests, workflow configuration, dependency failures, incorrect gates, missing production verification, branch-policy failures, or false-positive/false-negative CI checks.

A CI failure must first be classified as one of:

**Application / Test / Dependency / Infrastructure / Environment / Workflow-Governance**

### 4.12 Deployment/runtime defects
Failures that occur only after deployment, including incorrect environment variables, process configuration, routing, worker startup, health checks, runtime crashes, or production-only behavior.

### 4.13 Observability defects
Missing or misleading logs, metrics, traces, health signals, audit records, alerts, or diagnostic evidence.

### 4.14 Documentation/process defects
Incorrect runbooks, stale contracts, missing operational instructions, inaccurate phase gates, or procedures that permit unsafe/reproducible failure.

## 5. Severity

Severity describes technical/user/business impact. Priority describes how quickly the team should act. They must not be conflated.

### S0 — Critical
Immediate production safety, security, data-integrity, or platform-wide failure.

Examples:

- credentials or sensitive data exposed
- materially corrupted canonical market data
- production system producing systematically false intelligence
- authentication bypass
- persistent state corruption
- broad production outage with no safe fallback

**Expected response:** immediate investigation; release/merge blocked until controlled resolution or formally documented mitigation.

### S1 — High
Major production functionality is broken or materially unreliable, but scope or containment is narrower than S0.

Examples:

- primary market-data path fails without working fallback
- important research workflow returns materially incorrect results
- production portfolio/state synchronization fails
- critical scheduled job stops
- major authentication or billing/entitlement path fails

**Expected response:** expedited fix and verification; normally release-blocking for affected functionality.

### S2 — Medium
Meaningful defect with a workaround or limited impact.

Examples:

- one research workflow fails under a specific condition
- intermittent provider error with working fallback
- non-critical alert duplication
- UI state inconsistency without data corruption

**Expected response:** fix within the relevant development cycle.

### S3 — Low
Minor correctness, usability, documentation, or cosmetic issue with negligible production impact.

Examples:

- cosmetic UI issue
- non-critical copy error
- low-impact documentation gap

## 6. Priority

Use:

- **P0:** act immediately
- **P1:** next available engineering window
- **P2:** normal planned work
- **P3:** backlog/low urgency

Priority may be higher than severity when a lower-severity issue creates substantial operational risk or blocks a release.

## 7. Mandatory bug-report fields

Every bug report must contain:

### Identity
- Bug ID
- Title
- Status
- Severity
- Priority
- Primary defect class
- Secondary defect classes, if applicable
- Owner
- Reporter
- Date/time first observed

### Context
- Affected component/service
- Affected environment: local / CI / staging / production
- Exact application revision/commit
- Browser/device when relevant
- Provider/exchange when relevant
- Symbol/instrument
- Timeframe
- User/account role when relevant
- Feature/phase/release

### Reproduction
- Reproducibility: deterministic / intermittent / not reproduced
- Preconditions
- Exact reproduction steps
- Input/request/payload
- Expected behavior
- Actual behavior
- Frequency
- First known good revision
- First known bad revision when known

### Evidence
- Screenshots/video where useful
- Logs
- Stack traces
- API request/response evidence
- Provider response
- Provider timestamp
- Database/state evidence
- CI workflow/run
- Deployment revision
- Monitoring/health evidence

Do not place secrets, access tokens, passwords, or private credentials in a report.

### Impact
- User impact
- Market-data impact
- Quantitative/analytics impact
- Risk/alert impact
- Security impact
- Data-integrity impact
- Financial/billing impact
- Availability impact
- Scope: one user / cohort / feature / system-wide

### Resolution
- Root cause
- Contributing factors
- Fix description
- Changed files/components
- Regression test
- Additional tests
- CI evidence
- Production verification
- Monitoring added/updated
- Documentation/runbook updates
- Related PR/commit
- Resolution
- Closure evidence

## 8. Market-data integrity requirements

For defects involving live or near-live market data, reports must capture:

- instrument/symbol
- canonical symbol
- provider
- provider endpoint/feed
- provider quote timestamp
- server receipt timestamp when available
- requested timeframe
- observed freshness/age
- expected freshness policy
- OHLC/quote values relevant to the defect
- missing/duplicate/gap information
- primary/fallback provider state
- fallback-routing decision
- validation/scoring result
- whether stale/mock/simulated data was exposed to a production path

A quote must not be described as live solely because the application request succeeded.

## 9. Quantitative defect requirements

For indicator, scoring, signal, statistical, regime, or research defects, include:

1. input dataset/version
2. symbol and timeframe
3. calculation window
4. configuration/parameters
5. expected formula or contract
6. actual formula/result
7. numerical precision where relevant
8. NaN/Inf behavior
9. boundary/empty-data behavior
10. comparison with known-good/reference output
11. regression test proving the corrected behavior

Hardcoded test fixtures are acceptable for deterministic tests; production code paths must not silently substitute hardcoded or mock outputs for live data.

## 10. Risk and alert defect requirements

Reports must document:

- signal conditions
- risk conditions
- threshold/configuration values
- alert frequency
- deduplication behavior
- suppression/cooldown behavior
- volatility/regime conditions
- false-positive or false-negative evidence
- whether an alert could cause an unsafe downstream action
- whether any execution capability was unexpectedly reachable

Any unexpected path from research/signal logic into real trade execution is automatically at least a security/safety review item.

## 11. Database and state-recovery requirements

For persistence defects, capture:

- database/provider
- schema/table/entity
- record identifier where safe
- transaction boundaries
- migration version
- relevant indexes
- concurrency conditions
- cache involvement
- restart/redeploy conditions
- before/after state
- recovery behavior
- duplicate/lost/corrupted state evidence

A fix is incomplete if it repairs the normal path but loses state after restart or interruption.

## 12. Integration and notification requirements

For external integrations capture:

- integration/provider
- endpoint/event
- request ID/correlation ID where available
- HTTP/WebSocket status
- response/error
- timeout
- retry count
- backoff behavior
- rate-limit state
- queue state
- deduplication state
- final delivery state

For notifications, distinguish:

**generated → queued → dispatched → acknowledged/delivered**

Do not treat a locally generated notification as successfully delivered.

## 13. Security defect handling

Security-related reports must additionally record:

- affected trust boundary
- authentication state
- authorization/RBAC state
- data sensitivity
- exploit preconditions
- affected endpoint/component
- secret exposure status
- remediation
- regression/security test
- deployment verification

Never include credentials or exploitable secrets in issue text, logs, screenshots, fixtures, or test output.

## 14. CI/CD defect handling

When a workflow fails:

1. identify the exact workflow/run/job
2. capture the failing step
3. classify the failure
4. determine whether the failure reproduces locally
5. inspect recent code/dependency/workflow changes
6. determine whether the failure is a real application defect
7. fix the correct layer
8. rerun the relevant targeted test
9. rerun the complete required workflow
10. record the final green run

A green targeted test does not replace the required repository/phase CI gates.

## 15. Deployment and production verification

For production defects, record:

- deployment platform
- deployed revision
- deployment timestamp
- environment/configuration version where safely identifiable
- service/worker status
- health-check result
- relevant logs
- production reproduction
- production verification result
- rollback/mitigation status

Production verification must target the exact revision being certified.

## 16. Regression policy

Every resolved S0/S1 defect must normally have automated regression protection.

For S2/S3, automated regression coverage should be added when the defect is deterministic and technically testable.

Regression tests should prove the failure condition, not merely exercise the surrounding code.

Preferred sequence:

**Failing regression test → fix → regression passes → surrounding suite passes**

## 17. Root-cause analysis

The report must distinguish:

- **symptom:** what users/system operators observed
- **proximate cause:** immediate technical failure
- **root cause:** underlying condition that allowed the failure
- **contributing factors:** conditions that increased likelihood/impact
- **detection gap:** why existing tests/monitoring did not catch it
- **prevention:** control added to reduce recurrence

Avoid stopping at messages such as “API failed,” “test failed,” or “provider returned an error.”

## 18. Closure criteria

A defect may be closed only when all applicable requirements are satisfied:

- root cause identified or uncertainty explicitly documented
- fix implemented
- regression protection added where appropriate
- relevant tests pass
- required CI gates pass
- security review completed for security-impacting changes
- production verification completed for production-impacting changes
- monitoring/alerts updated where necessary
- documentation updated where necessary
- evidence attached/linked
- related PR/commit recorded

A defect is reopened if the same failure recurs, the fix is incomplete, or verification evidence is invalidated by a later deployment.

## 19. Duplicate and related defects

Before creating a new report:

- search existing open and recently closed defects
- link probable duplicates
- preserve the most complete report as the canonical record
- add new evidence to the canonical report when appropriate

Related defects should remain separately traceable when their root causes, owners, fixes, or verification paths differ.

## 20. Release-blocking rules

Default release blockers:

- S0
- S1
- unresolved security defects
- market-data integrity defects that can materially mislead users
- state/data corruption
- broken authentication/authorization
- broken production-critical provider routing
- failed required production verification
- failed mandatory CI/phase gates
- defects that invalidate a stated acceptance criterion

A release may proceed only when the blocker is fixed, safely mitigated under an explicit decision, or formally deferred with documented risk acceptance.

## 21. Evidence quality

Evidence should be:

**specific, reproducible, timestamped, revision-linked, and independently verifiable.**

Prefer:

- exact commit SHA
- exact workflow/run
- exact API response
- provider timestamp
- deterministic test
- production revision
- before/after state

Avoid:

- “works now”
- “fixed locally”
- screenshots without environment/revision context
- logs without timestamps
- test output without the command/revision
- claims that rely on memory rather than recorded evidence

## 22. Bug lifecycle states

Recommended state machine:

**New → Triaged → Reproducing → Confirmed → In Progress → Fixed → Verification → Closed**

Alternative states:

- **Blocked**
- **Cannot Reproduce**
- **Duplicate**
- **Won't Fix**
- **Deferred**
- **Reopened**

A status change should preserve the evidence supporting the transition.

## 23. Ownership and handoff

Each active defect should have one accountable owner.

Handoffs must preserve:

- current state
- reproduction status
- evidence
- suspected root cause
- tests already run
- remaining verification
- blockers
- next action

AI-assisted engineering may draft analysis or tests, but final defect disposition must be based on repository/runtime evidence rather than generated assumptions.

## 24. Standard bug-report template

Copy this template for each defect:

~~~markdown
# BUG-[ID] — [Short descriptive title]

## Classification
- Severity: S0/S1/S2/S3
- Priority: P0/P1/P2/P3
- Defect class:
- Status:
- Owner:
- Reporter:
- First observed:
- Environment:
- Revision/commit:
- Feature/phase/release:

## Impact
- User impact:
- Market-data impact:
- Analytics/signal impact:
- Risk/alert impact:
- Security impact:
- Data-integrity impact:
- Financial/billing impact:
- Availability impact:
- Scope:

## Context
- Symbol/instrument:
- Timeframe:
- Provider:
- Endpoint/workflow:
- User role:
- Browser/device:

## Reproduction
### Preconditions
-

### Steps
1.
2.
3.

### Expected
-

### Actual
-

### Reproducibility
- Deterministic / Intermittent / Not reproduced
- Frequency:

## Evidence
- Logs:
- Stack trace:
- API evidence:
- Provider timestamp:
- Database/state evidence:
- Screenshot/video:
- CI workflow/run:
- Deployment:

## Root Cause
- Symptom:
- Proximate cause:
- Root cause:
- Contributing factors:
- Detection gap:

## Resolution
- Fix:
- Changed components:
- Regression test:
- Additional tests:
- Monitoring changes:
- Documentation changes:

## Verification
- Targeted test:
- Full test suite:
- Build:
- Security checks:
- CI workflow/run:
- Production verification:
- Verified revision:

## Closure
- Resolution:
- Related PR:
- Related commit:
- Closure evidence:
- Closed by:
- Closed at:
~~~

## 25. Production incident extension

For S0/S1 incidents, add:

- incident start/end
- detection source
- affected services
- affected users/data
- timeline
- mitigation
- communications
- recovery
- permanent fix
- post-incident review
- prevention actions
- owners and due dates

Incident records should remain linked to the underlying defect rather than replacing it.

## 26. Rubric alignment

The supplied production market-intelligence evaluation rubric defines nine domains. This standard maps defect evidence to all nine:

| Rubric domain | Required defect evidence |
|---|---|
| Data ingestion & feed reliability | Provider, symbol, timestamp, freshness, gaps, fallback, reconnection/recovery |
| Quantitative analytics & signal engine | Inputs, parameters, formulas/contracts, numerical edge cases, reference output, regression test |
| Risk management & trade/alert logic | Risk conditions, thresholds, alert behavior, safety/execution-path assessment |
| Database architecture & state persistence | Schema/state, transaction behavior, restart/recovery, corruption/loss evidence |
| Integration/webhooks/notifications | Endpoint, payload, status, retry/backoff, queue, rate limit, delivery evidence |
| Security/environment configuration | Secrets, auth, RBAC, trust boundary, input validation, environment |
| Code maintainability & architecture | Component/layer, contract, coupling, affected modules, prevention |
| Testing/CI/CD/reliability | Reproduction test, regression test, targeted/full suite, CI run, failure classification |
| Deployment/cloud hosting | Exact deployed revision, runtime/worker state, environment, health and production verification |

## 27. Rubric-specific defect gates

A defect report must explicitly identify when it threatens one or more Level 4 production properties:

### Data
- hardcoded/mock production data
- stale-feed exposure
- missing reconnection
- missing timestamp synchronization
- undetected timeframe gaps

### Analytics
- hardcoded production signal outputs
- incorrect mathematical calculation
- NaN/Inf failure
- unvalidated edge case
- hidden magic-number behavior

### Risk/alerts
- missing dynamic risk calculation
- alert flood
- unsafe execution hook
- missing guardrail

### Persistence
- state loss after restart
- connection/resource leak
- migration failure
- corrupted or inconsistent state

### Integrations
- missing retry/backoff
- rate-limit failure
- notification delivery ambiguity
- missing heartbeat/health evidence

### Security
- secret exposure
- open protected endpoint
- missing authorization
- unsafe input handling

### Architecture
- duplicated business logic
- inappropriate coupling
- unmanaged global state
- dead or bypassed production code

### Reliability
- missing regression coverage
- workflow blind spot
- insufficient failure-mode testing
- unstructured or unavailable audit evidence

### Deployment
- environment drift
- worker/scheduler failure
- manual restart dependency
- production revision not verified

## 28. Definition of Done for a production bug

A production bug is **Done** only when:

1. The failure is understood.
2. The root cause is recorded.
3. The fix is implemented in the correct architectural layer.
4. The failure has regression protection when technically appropriate.
5. Relevant automated tests pass.
6. Required CI gates pass.
7. Security checks pass when applicable.
8. The deployed revision is verified when production behavior changed.
9. Monitoring/observability is sufficient to detect recurrence.
10. The evidence is linked to the defect record.
11. The change has entered the certified baseline through the repository's approved branch/PR process.

## 29. Anti-patterns explicitly prohibited

Do not close a defect because:

- the developer cannot reproduce it on their machine
- a single unit test passes
- the workflow was rerun without understanding the failure
- the production deployment was restarted
- the UI looks correct while underlying data is wrong
- a provider response was assumed to be current without checking its timestamp
- a fallback was assumed to work without verifying the routing contract
- logs were deleted or overwritten before investigation
- a failure was classified as “flaky” without evidence
- a hotfix was pushed directly to `main`
- an AI-generated explanation was accepted without repository/runtime evidence

## 30. Review and continuous improvement

The document itself should be reviewed after:

- every S0/S1 incident
- repeated recurrence of the same defect class
- major architecture changes
- new market-data providers
- new deployment infrastructure
- major authentication/billing changes
- material changes to CI/phase governance

Post-incident findings should update the defect taxonomy, required evidence, tests, monitoring, or release gates where appropriate.

---

## Appendix A — Compact triage checklist

**Impact**
- [ ] Is production affected?
- [ ] Is data incorrect or stale?
- [ ] Is security affected?
- [ ] Is state at risk?
- [ ] Is risk/alert behavior affected?
- [ ] Is a release blocked?

**Reproduction**
- [ ] Exact revision captured
- [ ] Environment captured
- [ ] Preconditions captured
- [ ] Reproduction attempted
- [ ] Expected vs actual recorded

**Diagnosis**
- [ ] Defect class assigned
- [ ] Root cause identified
- [ ] Detection gap identified
- [ ] Related defects searched

**Fix**
- [ ] Correct architectural layer changed
- [ ] Regression test added
- [ ] Security implications checked
- [ ] Monitoring/documentation considered

**Verification**
- [ ] Targeted tests pass
- [ ] Full required tests pass
- [ ] CI green
- [ ] Production revision verified where applicable
- [ ] Evidence linked

**Closure**
- [ ] Resolution recorded
- [ ] Related PR/commit linked
- [ ] Closure criteria satisfied
- [ ] Owner/date recorded
