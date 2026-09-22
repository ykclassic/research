-- Phase 3: market scanner, saved scanners, schedules and durable opportunity history.

create table if not exists public.scanner_presets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  description text not null default '',
  asset_universe jsonb not null default '[]'::jsonb,
  timeframes jsonb not null default '["15m","1h","4h","1D"]'::jsonb,
  conditions jsonb not null default '{}'::jsonb,
  alert_events jsonb not null default '[]'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.scanner_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preset_id uuid not null references public.scanner_presets(id) on delete cascade,
  status text not null check (status in ('RUNNING','COMPLETED','FAILED')),
  scanned_count integer not null default 0 check (scanned_count >= 0),
  qualified_count integer not null default 0 check (qualified_count >= 0),
  started_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz
);

create table if not exists public.scanner_opportunities (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.scanner_runs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  setup text not null,
  regime text,
  direction text not null,
  confidence numeric not null check (confidence between 0 and 1),
  risk_reward numeric check (risk_reward >= 0),
  structure text,
  liquidity text,
  mtf_alignment integer check (mtf_alignment between 0 and 4),
  momentum numeric,
  volatility numeric check (volatility >= 0),
  volume numeric check (volume >= 0),
  signal_status text not null,
  historical_evidence jsonb not null default '{}'::jsonb,
  signal_id uuid,
  observed_at timestamptz not null,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.scanner_schedules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preset_id uuid not null references public.scanner_presets(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  interval_minutes integer not null check (interval_minutes between 15 and 10080),
  enabled boolean not null default true,
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists scanner_presets_user_idx on public.scanner_presets(user_id, enabled, created_at desc);
create index if not exists scanner_runs_user_idx on public.scanner_runs(user_id, started_at desc);
create index if not exists scanner_opportunities_user_observed_idx on public.scanner_opportunities(user_id, observed_at desc);
create index if not exists scanner_opportunities_symbol_idx on public.scanner_opportunities(user_id, symbol, observed_at desc);
create index if not exists scanner_schedules_due_idx on public.scanner_schedules(enabled, next_run_at);
create index if not exists scanner_schedules_user_idx on public.scanner_schedules(user_id, created_at desc);

create or replace function public.set_scanner_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = timezone('utc', now()); return new; end;
$$;

drop trigger if exists scanner_presets_updated_at on public.scanner_presets;
create trigger scanner_presets_updated_at before update on public.scanner_presets for each row execute function public.set_scanner_updated_at();

drop trigger if exists scanner_schedules_updated_at on public.scanner_schedules;
create trigger scanner_schedules_updated_at before update on public.scanner_schedules for each row execute function public.set_scanner_updated_at();

alter table public.scanner_presets enable row level security;
alter table public.scanner_runs enable row level security;
alter table public.scanner_opportunities enable row level security;
alter table public.scanner_schedules enable row level security;

grant select, insert, update, delete on public.scanner_presets to authenticated;
grant select, insert, update, delete on public.scanner_runs to authenticated;
grant select, insert, update, delete on public.scanner_opportunities to authenticated;
grant select, insert, update, delete on public.scanner_schedules to authenticated;

drop policy if exists scanner_presets_select_own on public.scanner_presets;
create policy scanner_presets_select_own on public.scanner_presets for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists scanner_presets_insert_own on public.scanner_presets;
create policy scanner_presets_insert_own on public.scanner_presets for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists scanner_presets_update_own on public.scanner_presets;
create policy scanner_presets_update_own on public.scanner_presets for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists scanner_presets_delete_own on public.scanner_presets;
create policy scanner_presets_delete_own on public.scanner_presets for delete to authenticated using ((select auth.uid()) = user_id);

drop policy if exists scanner_runs_select_own on public.scanner_runs;
create policy scanner_runs_select_own on public.scanner_runs for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists scanner_runs_insert_own on public.scanner_runs;
create policy scanner_runs_insert_own on public.scanner_runs for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists scanner_runs_update_own on public.scanner_runs;
create policy scanner_runs_update_own on public.scanner_runs for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists scanner_opportunities_select_own on public.scanner_opportunities;
create policy scanner_opportunities_select_own on public.scanner_opportunities for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists scanner_opportunities_insert_own on public.scanner_opportunities;
create policy scanner_opportunities_insert_own on public.scanner_opportunities for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists scanner_schedules_select_own on public.scanner_schedules;
create policy scanner_schedules_select_own on public.scanner_schedules for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists scanner_schedules_insert_own on public.scanner_schedules;
create policy scanner_schedules_insert_own on public.scanner_schedules for insert to authenticated with check ((select auth.uid()) = user_id);
drop policy if exists scanner_schedules_update_own on public.scanner_schedules;
create policy scanner_schedules_update_own on public.scanner_schedules for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists scanner_schedules_delete_own on public.scanner_schedules;
create policy scanner_schedules_delete_own on public.scanner_schedules for delete to authenticated using ((select auth.uid()) = user_id);

grant select, insert, update, delete on public.scanner_presets, public.scanner_runs, public.scanner_opportunities, public.scanner_schedules to service_role;


create table if not exists public.scanner_alert_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  preset_id uuid not null references public.scanner_presets(id) on delete cascade,
  opportunity_id uuid references public.scanner_opportunities(id) on delete set null,
  event_type text not null,
  symbol text not null,
  title text not null,
  message text not null,
  payload jsonb not null default '{}'::jsonb,
  triggered_at timestamptz not null default timezone('utc', now()),
  read_at timestamptz,
  fingerprint text not null,
  unique(user_id, preset_id, fingerprint)
);

create index if not exists scanner_alert_events_user_idx
  on public.scanner_alert_events(user_id, triggered_at desc);
create index if not exists scanner_alert_events_unread_idx
  on public.scanner_alert_events(user_id, read_at, triggered_at desc);

alter table public.scanner_alert_events enable row level security;
grant select, update on public.scanner_alert_events to authenticated;
grant select, insert, update on public.scanner_alert_events to service_role;

drop policy if exists scanner_alert_events_select_own on public.scanner_alert_events;
create policy scanner_alert_events_select_own
  on public.scanner_alert_events for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists scanner_alert_events_update_own on public.scanner_alert_events;
create policy scanner_alert_events_update_own
  on public.scanner_alert_events for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
