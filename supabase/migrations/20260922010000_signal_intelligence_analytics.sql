-- Phase 2: Signal Intelligence, Outcome Analytics & Calibration.
-- Stores immutable signal-state snapshots alongside the outcome audit.
create table if not exists public.signal_intelligence (
  id uuid primary key default gen_random_uuid(),
  signal_id uuid not null,
  revision integer not null check (revision >= 1),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  direction text not null,
  dispatched_at timestamptz not null,
  entry_price numeric(30,12) not null check (entry_price > 0),
  stop_loss numeric(30,12) not null check (stop_loss > 0),
  target_price numeric(30,12) not null check (target_price > 0),
  risk_reward numeric(20,10),
  timeframe text not null,
  mtf_bias text,
  mtf_alignment integer check (mtf_alignment between 0 and 4),
  regime text,
  regime_confidence numeric(12,10),
  market_structure text,
  liquidity_conditions text,
  momentum numeric(12,10),
  volatility numeric(20,10),
  session text,
  strategy text not null default 'signal_engine',
  confidence numeric(12,10) not null check (confidence between 0 and 1),
  outcome text not null default 'PENDING',
  target_timestamp timestamptz,
  stop_timestamp timestamptz,
  first_touch_timestamp timestamptz,
  r_result numeric(20,10),
  outcome_latency_seconds double precision,
  signal_engine_version text not null,
  evidence jsonb not null default '[]'::jsonb,
  replay_candles jsonb not null default '[]'::jsonb,
  structural_conditions jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  unique(signal_id, revision)
);
create index if not exists signal_intelligence_filter_idx
  on public.signal_intelligence(user_id, dispatched_at desc);
create index if not exists signal_intelligence_dimensions_idx
  on public.signal_intelligence(user_id, symbol, timeframe, regime, strategy, signal_engine_version);
create index if not exists signal_intelligence_confidence_idx
  on public.signal_intelligence(user_id, confidence, risk_reward);
alter table public.signal_intelligence enable row level security;
revoke all on table public.signal_intelligence from anon, authenticated;
grant select, insert on table public.signal_intelligence to authenticated;
drop policy if exists "signal_intelligence_select_own" on public.signal_intelligence;
create policy "signal_intelligence_select_own" on public.signal_intelligence
  for select to authenticated using ((select auth.uid()) = user_id);
drop policy if exists "signal_intelligence_insert_own" on public.signal_intelligence;
create policy "signal_intelligence_insert_own" on public.signal_intelligence
  for insert to authenticated with check ((select auth.uid()) = user_id);

insert into public.billing_features(id,name,description,category)
values ('signal_intelligence_analytics','Signal intelligence analytics','Historical signal performance, replay, calibration and similarity analytics.','INTELLIGENCE')
on conflict (id) do update set name=excluded.name, description=excluded.description, category=excluded.category;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
values
 ('free','signal_intelligence_analytics',false),
 ('pro','signal_intelligence_analytics',true),
 ('premium','signal_intelligence_analytics',true)
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;

create index if not exists signal_outcome_audit_signal_user_dispatch_idx
  on public.signal_outcome_audit(user_id, dispatched_at desc);
