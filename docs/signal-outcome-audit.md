# Signal Outcome & Target-Tag Audit

## Activation rule

A signal is not audited merely because the deterministic engine generated it. The audit begins only when an authenticated user clicks **Log Signal** on the Signals page. The backend server stamps `dispatched_at` at the log request; the browser cannot choose that timestamp.

## Immutable evidence

`signal_audit_records` is the immutable signal snapshot. It preserves the signal identity, score, confidence, entry, stop, target, provider, monitoring timeframe, calculation timestamps, dispatch timestamp, and signal-engine version. There are no authenticated UPDATE or DELETE privileges for this table, and a database trigger rejects mutation attempts as defense in depth.

`signal_audit_outcomes` is append-only. At most one terminal outcome is recorded for each logged signal.

## First-touch rule

Outcome evaluation uses completed 15-minute OHLC candles after `dispatched_at`:

- BUY / STRONG_BUY: target is touched when `high >= target`; stop when `low <= stop`.
- SELL / STRONG_SELL: target is touched when `low <= target`; stop when `high >= stop`.
- The first post-dispatch candle that touches exactly one terminal level determines the outcome.
- If both target and stop are touched in the same candle, the outcome is `AMBIGUOUS`. OHLC data cannot prove which level was reached first inside that candle, so the system does not invent an intrabar ordering.
- The signal candle and all candles at or before `dispatched_at` are excluded.

`target_tagged_at` / `stop_tagged_at` and their latency values use the timestamp of the first completed candle that proves the touch. This is an observation timestamp, not an invented exact tick timestamp. Exact intrabar latency requires a higher-resolution trade/quote feed.

## UI

- Signals page: **Log Signal** creates the immutable audit snapshot.
- Signals page: **Signal Outcome** opens `/analysis/signals/outcomes`.
- Signal Outcome page shows the logged signal, target/stop, dispatch time, first-touch information, and current status: Pending, Take profit hit, Stop loss hit, or Ambiguous.
- Refreshing a pending record evaluates current completed candles. A signal that was never logged is never queried by the outcome-audit evaluator.

## Calibration boundary

This audit deliberately does not modify signal thresholds, scoring weights, ATR stop multipliers, structural-target selection, or qualification logic. Its purpose is to create chronological outcome evidence that can later support walk-forward calibration without fitting parameters to a single live sample.

## Production gate

The migration `supabase/migrations/20260919160000_signal_outcome_audit.sql` must be applied to the production Supabase project before this phase is considered production-certified. CI passing only verifies application code; it does not prove that the production database schema exists.