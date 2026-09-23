-- Phase 5: grounded AI research runs, schedules and tiered copilot capabilities.

create table if not exists public.research_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  query text not null check (char_length(trim(query)) between 3 and 4000),
  assets jsonb not null default '[]'::jsonb,
  timeframe text not null default '1h',
  market_snapshot jsonb not null default '{}'::jsonb,
  feature_snapshot jsonb not null default '{}'::jsonb,
  regime_snapshot jsonb not null default '{}'::jsonb,
  signal_state jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '[]'::jsonb,
  sources jsonb not null default '[]'::jsonb,
  model text not null,
  model_version text not null,
  engine_version text not null,
  generated_report text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists research_runs_user_time_idx on public.research_runs(user_id, created_at desc);
create index if not exists research_runs_asset_time_idx on public.research_runs using gin(assets);

alter table public.research_runs enable row level security;
grant select, insert on public.research_runs to authenticated;
grant select, insert on public.research_runs to service_role;

drop policy if exists research_runs_own on public.research_runs;
create policy research_runs_own on public.research_runs for select to authenticated
using ((select auth.uid()) = user_id);
create policy research_runs_insert_own on public.research_runs for insert to authenticated
with check ((select auth.uid()) = user_id);

create table if not exists public.research_schedules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  query text not null check (char_length(trim(query)) between 3 and 4000),
  interval_minutes integer not null check (interval_minutes between 60 and 10080),
  enabled boolean not null default true,
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists research_schedules_due_idx on public.research_schedules(next_run_at) where enabled = true;
create index if not exists research_schedules_user_idx on public.research_schedules(user_id, created_at desc);

alter table public.research_schedules enable row level security;
grant select, insert, update, delete on public.research_schedules to authenticated;
grant select, insert, update on public.research_schedules to service_role;

drop policy if exists research_schedules_own on public.research_schedules;
create policy research_schedules_own on public.research_schedules for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

insert into public.billing_features(id,name,description,category) values
 ('copilot_deep_research','Deep AI research','Expanded historical retrieval and deeper grounded analysis.','INTELLIGENCE'),
 ('copilot_multi_step','Multi-step research agents','Multi-step research workflows over structured platform evidence.','INTELLIGENCE')
on conflict (id) do update set name=excluded.name,description=excluded.description,category=excluded.category;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
values
 ('free','copilot_deep_research',false),('free','copilot_multi_step',false),
 ('pro','copilot_deep_research',true),('pro','copilot_multi_step',false),
 ('premium','copilot_deep_research',true),('premium','copilot_multi_step',true)
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;

insert into public.billing_plan_limits(plan_id,metric,limit_value)
values
 ('free','copilot_research_runs',5),
 ('pro','copilot_research_runs',100),
 ('premium','copilot_research_runs',500)
on conflict (plan_id,metric) do update set limit_value=excluded.limit_value;
