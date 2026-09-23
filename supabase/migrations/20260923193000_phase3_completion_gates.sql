-- Phase 3 completion gates: durable scheduler claims and delivery retry indexing.
-- Scheduler claims are implemented with a conditional PATCH in the service so
-- overlapping GitHub Actions invocations cannot execute the same due schedule.
-- Failed EMAIL deliveries remain retryable while the alert itself remains
-- deduplicated by (alert_id, channel).

create index if not exists scanner_alert_deliveries_retry_idx
  on public.scanner_alert_deliveries(attempted_at asc)
  where channel = 'EMAIL' and status = 'FAILED';

create index if not exists scanner_schedules_due_idx
  on public.scanner_schedules(next_run_at)
  where enabled = true;
