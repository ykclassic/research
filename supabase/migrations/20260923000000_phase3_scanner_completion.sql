-- Phase 3 completion: scanner state, explicit trend/levels, and auditable delivery attempts.

alter table public.scanner_opportunities
  add column if not exists trend text,
  add column if not exists entry_price numeric,
  add column if not exists stop_loss numeric,
  add column if not exists target_price numeric,
  add column if not exists last_price numeric,
  add column if not exists structural_conditions jsonb not null default '{}'::jsonb;

create index if not exists scanner_opportunities_target_state_idx
  on public.scanner_opportunities(user_id, symbol, observed_at desc)
  where target_price is not null or stop_loss is not null;

create table if not exists public.scanner_alert_deliveries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  alert_id uuid not null references public.scanner_alert_events(id) on delete cascade,
  channel text not null check (channel in ('WEB','EMAIL')),
  status text not null check (status in ('SENT','SKIPPED','FAILED')),
  attempted_at timestamptz not null default timezone('utc', now()),
  error text,
  unique(alert_id, channel)
);

create index if not exists scanner_alert_deliveries_user_idx
  on public.scanner_alert_deliveries(user_id, attempted_at desc);

alter table public.scanner_alert_deliveries enable row level security;
grant select on public.scanner_alert_deliveries to authenticated;
grant select, insert, update on public.scanner_alert_deliveries to service_role;

drop policy if exists scanner_alert_deliveries_select_own on public.scanner_alert_deliveries;
create policy scanner_alert_deliveries_select_own
  on public.scanner_alert_deliveries for select to authenticated
  using ((select auth.uid()) = user_id);
