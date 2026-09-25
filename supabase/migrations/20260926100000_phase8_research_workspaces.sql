create table if not exists public.research_workspaces (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  workspace_type text not null default 'THEME' check (workspace_type in ('CRYPTO','EQUITIES','FX','SECTOR','STRATEGY','THEME','PORTFOLIO','CUSTOM')),
  description text not null default '' check (char_length(description) <= 1000),
  shared boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create table if not exists public.research_workspace_assets (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null check (char_length(trim(symbol)) between 1 and 32),
  role text not null default 'PRIMARY' check (role in ('PRIMARY','COMPARISON','BENCHMARK','WATCH')),
  created_at timestamptz not null default timezone('utc', now()),
  unique(workspace_id, symbol)
);
create table if not exists public.research_workspace_dashboards (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  layout jsonb not null default '{"columns":12,"rows":[]}'::jsonb,
  widgets jsonb not null default '[]'::jsonb,
  saved_views jsonb not null default '[]'::jsonb,
  custom_metrics jsonb not null default '[]'::jsonb,
  shared boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create table if not exists public.research_workspace_links (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  resource_type text not null check (resource_type in ('WATCHLIST','RESEARCH_RUN','REPORT','ALERT','WATCHPOINT','EXPERIMENT')),
  resource_id uuid not null,
  created_at timestamptz not null default timezone('utc', now()),
  unique(workspace_id, resource_type, resource_id)
);
create table if not exists public.research_scorecards (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  factors jsonb not null default '[]'::jsonb,
  conditions jsonb not null default '[]'::jsonb,
  thresholds jsonb not null default '{}'::jsonb,
  scoring_rules jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create table if not exists public.research_automation_rules (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  trigger_type text not null check (trigger_type in ('SCHEDULE','REGIME_CHANGE','PRICE_THRESHOLD','SCORE_THRESHOLD','WATCHPOINT')),
  schedule_cron text,
  symbol text,
  condition jsonb not null default '{}'::jsonb,
  action jsonb not null default '{"type":"RESEARCH_RUN"}'::jsonb,
  enabled boolean not null default true,
  last_triggered_at timestamptz,
  next_run_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  check ((trigger_type = 'SCHEDULE' and schedule_cron is not null) or trigger_type <> 'SCHEDULE')
);
create table if not exists public.research_cross_asset_runs (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.research_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  symbols jsonb not null default '[]'::jsonb,
  timeframe text not null default '1d',
  correlation_matrix jsonb not null default '{}'::jsonb,
  relationships jsonb not null default '[]'::jsonb,
  factor_relationships jsonb not null default '[]'::jsonb,
  regime_relationships jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists research_workspaces_user_idx on public.research_workspaces(user_id, updated_at desc);
create index if not exists research_workspace_assets_user_idx on public.research_workspace_assets(user_id, workspace_id);
create index if not exists research_workspace_dashboards_user_idx on public.research_workspace_dashboards(user_id, workspace_id);
create index if not exists research_workspace_links_user_idx on public.research_workspace_links(user_id, workspace_id);
create index if not exists research_scorecards_user_idx on public.research_scorecards(user_id, workspace_id);
create index if not exists research_automation_rules_due_idx on public.research_automation_rules(enabled, next_run_at) where enabled = true;
create index if not exists research_cross_asset_runs_user_idx on public.research_cross_asset_runs(user_id, created_at desc);

alter table public.research_workspaces enable row level security;
alter table public.research_workspace_assets enable row level security;
alter table public.research_workspace_dashboards enable row level security;
alter table public.research_workspace_links enable row level security;
alter table public.research_scorecards enable row level security;
alter table public.research_automation_rules enable row level security;
alter table public.research_cross_asset_runs enable row level security;

drop policy if exists research_workspaces_own on public.research_workspaces;
create policy research_workspaces_own on public.research_workspaces for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_workspace_assets_own on public.research_workspace_assets;
create policy research_workspace_assets_own on public.research_workspace_assets for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_workspace_dashboards_own on public.research_workspace_dashboards;
create policy research_workspace_dashboards_own on public.research_workspace_dashboards for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_workspace_links_own on public.research_workspace_links;
create policy research_workspace_links_own on public.research_workspace_links for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_scorecards_own on public.research_scorecards;
create policy research_scorecards_own on public.research_scorecards for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_automation_rules_own on public.research_automation_rules;
create policy research_automation_rules_own on public.research_automation_rules for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists research_cross_asset_runs_own on public.research_cross_asset_runs;
create policy research_cross_asset_runs_own on public.research_cross_asset_runs for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);