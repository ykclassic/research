-- Canonical Phase 2 Signal Intelligence schema.
-- The production table was initially created outside repository migration history.
-- This migration is intentionally idempotent so it can reconcile that existing
-- table while making the schema reproducible for fresh environments.

create table if not exists public.signal_intelligence (
  id uuid primary key default gen_random_uuid(),
  signal_id uuid not null,
  revision integer not null check (revision >= 1),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  direction text not null,
  dispatched_at timestamptz not null,
  entry_price numeric not null check (entry_price > 0),
  stop_loss numeric not null check (stop_loss > 0),
  target_price numeric not null check (target_price > 0),
  risk_reward numeric,
  timeframe text not null,
  mtf_bias text,
  mtf_alignment integer check (mtf_alignment >= 0 and mtf_alignment <= 4),
  regime text,
  regime_confidence numeric,
  market_structure text,
  liquidity_conditions text,
  momentum numeric,
  volatility numeric,
  session text,
  strategy text not null default 'signal_engine',
  confidence numeric not null check (confidence >= 0 and confidence <= 1),
  outcome text not null default 'PENDING',
  target_timestamp timestamptz,
  stop_timestamp timestamptz,
  first_touch_timestamp timestamptz,
  r_result numeric,
  outcome_latency_seconds double precision,
  signal_engine_version text not null,
  evidence jsonb not null default '[]'::jsonb,
  replay_candles jsonb not null default '[]'::jsonb,
  structural_conditions jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  constraint signal_intelligence_signal_id_revision_key unique (signal_id, revision)
);

create index if not exists signal_intelligence_filter_idx
  on public.signal_intelligence (user_id, dispatched_at desc);

create index if not exists signal_intelligence_dimensions_idx
  on public.signal_intelligence (user_id, symbol, timeframe, regime, strategy, signal_engine_version);

create index if not exists signal_intelligence_confidence_idx
  on public.signal_intelligence (user_id, confidence, risk_reward);

alter table public.signal_intelligence enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'signal_intelligence'
      and policyname = 'signal_intelligence_select_own'
  ) then
    create policy signal_intelligence_select_own
      on public.signal_intelligence
      for select
      to authenticated
      using (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'signal_intelligence'
      and policyname = 'signal_intelligence_insert_own'
  ) then
    create policy signal_intelligence_insert_own
      on public.signal_intelligence
      for insert
      to authenticated
      with check (auth.uid() = user_id);
  end if;
end
$$;

grant select, insert on public.signal_intelligence to authenticated;
grant all on public.signal_intelligence to service_role;
