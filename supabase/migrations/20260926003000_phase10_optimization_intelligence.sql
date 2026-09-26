-- Phase 10: advanced charting, fundamentals, model governance, caching and product telemetry.
create table if not exists public.research_chart_events (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null, timeframe text not null,
  event_type text not null check (event_type in ('REGIME','SMC','BOS','CHOCH','LIQUIDITY','SIGNAL','ENTRY','EXIT','SL','TP','OUTCOME','RESEARCH','CATALYST')),
  occurred_at timestamptz not null, price numeric, payload jsonb not null default '{}'::jsonb, source text, engine_version text,
  created_at timestamptz not null default timezone('utc',now())
);
create index if not exists research_chart_events_lookup on public.research_chart_events(user_id,symbol,timeframe,occurred_at desc);

create table if not exists public.fundamental_observations (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null, observation_type text not null check (observation_type in ('FINANCIAL_STATEMENT','EARNINGS','VALUATION','ANALYST_REVISION','CORPORATE_ACTION','FUNDAMENTAL_TREND')),
  period_start date, period_end date, observed_at timestamptz not null default timezone('utc',now()), source text, source_version text,
  payload jsonb not null default '{}'::jsonb, created_at timestamptz not null default timezone('utc',now())
);
create index if not exists fundamental_observations_lookup on public.fundamental_observations(user_id,symbol,observation_type,observed_at desc);

create table if not exists public.research_models (
  id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 160),
  model_type text not null check (model_type in ('SIGNAL_CALIBRATION','QUALITY_SCORING','SIMILARITY','REGIME_CONDITIONED','PREDICTIVE')),
  description text, active_version_id uuid, created_at timestamptz not null default timezone('utc',now()), updated_at timestamptz not null default timezone('utc',now())
);

create table if not exists public.research_model_versions (
  id uuid primary key default gen_random_uuid(), model_id uuid not null references public.research_models(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade, version text not null,
  status text not null default 'DRAFT' check (status in ('DRAFT','VALIDATING','APPROVED','RETIRED','ROLLED_BACK')),
  dataset_version text not null, feature_version text not null,
  training_period_start date not null, training_period_end date not null,
  validation_period_start date not null, validation_period_end date not null,
  test_period_start date not null, test_period_end date not null,
  calibration jsonb not null default '{}'::jsonb, test_results jsonb not null default '{}'::jsonb,
  performance_by_regime jsonb not null default '{}'::jsonb, degradation_monitoring jsonb not null default '{}'::jsonb,
  test_passed boolean not null default false, promotion_actor_user_id uuid references auth.users(id), promoted_at timestamptz,
  rollback_reason text, created_at timestamptz not null default timezone('utc',now()), updated_at timestamptz not null default timezone('utc',now()),
  unique(model_id,version), check (training_period_start <= training_period_end), check (validation_period_start <= validation_period_end), check (test_period_start <= test_period_end),
  check (status <> 'APPROVED' or (test_passed = true and promotion_actor_user_id is not null and promoted_at is not null))
);
create index if not exists research_model_versions_lookup on public.research_model_versions(user_id,model_id,created_at desc);

create table if not exists public.research_model_events (
  id uuid primary key default gen_random_uuid(), model_version_id uuid not null references public.research_model_versions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade, event_type text not null check (event_type in ('CREATED','VALIDATION_STARTED','EVALUATED','PROMOTED','ROLLED_BACK','RETIRED')),
  actor_user_id uuid not null references auth.users(id), details jsonb not null default '{}'::jsonb, created_at timestamptz not null default timezone('utc',now())
);

create table if not exists public.research_cache_entries (
  cache_key text primary key, namespace text not null, payload jsonb not null, version text not null, expires_at timestamptz not null,
  created_at timestamptz not null default timezone('utc',now()), updated_at timestamptz not null default timezone('utc',now())
);
create index if not exists research_cache_expiry on public.research_cache_entries(expires_at);

create table if not exists public.product_events (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete set null,
  event_name text not null, feature text, properties jsonb not null default '{}'::jsonb, occurred_at timestamptz not null default timezone('utc',now())
);
create index if not exists product_events_feature_time on public.product_events(feature,occurred_at desc);
create index if not exists product_events_user_time on public.product_events(user_id,occurred_at desc);

alter table public.research_chart_events enable row level security;
alter table public.fundamental_observations enable row level security;
alter table public.research_models enable row level security;
alter table public.research_model_versions enable row level security;
alter table public.research_model_events enable row level security;
alter table public.product_events enable row level security;
create policy phase10_chart_events_own on public.research_chart_events for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy phase10_fundamentals_own on public.fundamental_observations for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy phase10_models_own on public.research_models for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy phase10_model_versions_own on public.research_model_versions for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy phase10_model_events_own on public.research_model_events for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy phase10_product_events_own on public.product_events for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
revoke all on public.research_cache_entries from anon,authenticated;
grant all on public.research_cache_entries to service_role;

insert into public.billing_features(id,name,description,category)
values ('phase10_intelligence','Optimization & Advanced Intelligence','Advanced charting, fundamentals, model governance, product intelligence and platform optimization.','INTELLIGENCE')
on conflict (id) do update set name=excluded.name,description=excluded.description,category=excluded.category;
insert into public.billing_plan_features(plan_id,feature_id,enabled)
values ('free','phase10_intelligence',false),('pro','phase10_intelligence',true),('premium','phase10_intelligence',true)
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;
