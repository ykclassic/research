-- Phase 4 completion gates: model provenance and first-class catalyst/event persistence.

alter table public.research_provenance
  add column if not exists model_version text not null default 'deterministic-research';

create index if not exists research_provenance_model_idx
  on public.research_provenance(user_id, snapshot_id, model_version);

create table if not exists public.research_catalyst_events (
    id text primary key,
    symbol text,
    user_id uuid not null references auth.users(id) on delete cascade,
    title text not null,
    event_type text not null,
    source text not null,
    source_url text,
    event_timestamp timestamptz not null,
    affected_assets jsonb not null default '[]'::jsonb,
    sentiment text,
    market_reaction jsonb not null default '{}'::jsonb,
    provider text not null,
    actual numeric,
    estimate numeric,
    previous numeric,
    surprise numeric,
    observed_at timestamptz not null default timezone('utc', now())
);

create index if not exists research_catalyst_user_time_idx
  on public.research_catalyst_events(user_id, event_timestamp desc);

create index if not exists research_catalyst_symbol_time_idx
  on public.research_catalyst_events(symbol, event_timestamp desc);

alter table public.research_catalyst_events enable row level security;
revoke all on table public.research_catalyst_events from anon;
grant select, insert, update on table public.research_catalyst_events to authenticated;
grant select, insert, update on table public.research_catalyst_events to service_role;

drop policy if exists research_catalyst_own on public.research_catalyst_events;
create policy research_catalyst_own
  on public.research_catalyst_events for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
