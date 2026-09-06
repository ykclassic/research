# Phase 12 — Alerts & Monitoring

Alerts are deterministic observations over the canonical market-data, technical-analysis, regime, and market-structure engines. They do not create trade signals, authorize execution, or execute orders.

## Supported rules

- `RSI_THRESHOLD`: RSI(14) crosses into a configured `<`, `<=`, `>`, or `>=` state.
- `PRICE_CROSS`: price crosses a configured level from below or above.
- `REGIME_CHANGE`: the deterministic market regime changes between completed observations.
- `BULLISH_BOS`: a new confirmed bullish BOS is detected by the existing market-structure engine.

Rules are evaluated against completed candles. Price-cross alerts require a prior observed price so creating a rule does not immediately fire an alert simply because the current price is already beyond the level.

## Persistence and security

`alert_rules` and `alert_events` are user-owned Supabase tables protected by RLS. Backend requests use the authenticated user's existing access token; no service-role credential is introduced.

The event table has a `(rule_id, fingerprint)` uniqueness constraint to prevent duplicate notifications for the same market observation. Cooldowns provide an additional user-configurable suppression window.

## Monitoring model

The current web channel uses an authenticated browser check every 60 seconds while the Alerts workspace is open, plus a manual **Check now** action. Triggered events are persisted so the notification history survives page refreshes. Browser notifications use the standard Web Notifications API when the user grants permission.

This intentionally does not claim always-on background monitoring: a production always-on worker/push service can be added later without changing the rule or event model. Email and Discord are represented as extensible channel values but are not sent until their delivery adapters are implemented.

## API

- `GET /api/alerts` — list rules
- `POST /api/alerts` — create rule
- `GET /api/alerts/{id}` — get rule
- `PATCH /api/alerts/{id}` — update rule
- `DELETE /api/alerts/{id}` — delete rule
- `GET /api/alerts/events/list` — list notification events
- `POST /api/alerts/events/evaluate` — evaluate the authenticated user's enabled rules
- `POST /api/alerts/events/{id}/read` — mark an event read

## Production gate

The Supabase migration `20260906190000_alerts_monitoring.sql` must be applied to the production project before the persistence path is considered production-verified. The repository migration is versioned so it can be applied through the existing Supabase deployment process.
