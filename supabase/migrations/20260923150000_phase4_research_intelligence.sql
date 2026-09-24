-- Phase 4: persistent research intelligence, provenance and watchpoints.

create table if not exists public.research_snapshots (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    symbol text not null,
    snapshot_type text not null check (snapshot_type in ('REPORT','SESSION','DAILY','WEEKLY','SAVED')),
    snapshot_at timestamptz not null,
    source_history_id uuid references public.research_history(id) on delete set null,
    state jsonb not null default '{}'::jsonb,
    engine_version text not null,
    created_at timestamptz not null default timezone('utc', now()),
    constraint research_snapshots_symbol_length check (char_length(trim(symbol)) between 1 and 32),
    constraint research_snapshots_state_object check (jsonb_typeof(state) = 'object')
);

create index if not exists research_snapshots_user_symbol_time_idx
    on public.research_snapshots (user_id, symbol, snapshot_at desc);

create table if not exists public.research_provenance (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    snapshot_id uuid not null references public.research_snapshots(id) on delete cascade,
    claim_type text not null,
    claim text not null,
    analysis text not null,
    data jsonb not null default '{}'::jsonb,
    sources jsonb not null default '[]'::jsonb,
    observed_at timestamptz not null,
    method text not null,
    engine_version text not null
);

create index if not exists research_provenance_snapshot_idx
    on public.research_provenance (user_id, snapshot_id, observed_at);

create table if not exists public.research_watchpoints (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    symbol text not null,
    name text not null,
    condition_type text not null check (condition_type in ('FIELD_THRESHOLD','FIELD_EQUALS','SUPPORT_LOSS','REGIME_CHANGE')),
    field text not null,
    operator text not null check (operator in ('eq','gt','gte','lt','lte')),
    value jsonb,
    timeframe text,
    enabled boolean not null default true,
    last_state boolean,
    last_triggered_at timestamptz,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint research_watchpoints_symbol_length check (char_length(trim(symbol)) between 1 and 32)
);

create index if not exists research_watchpoints_user_symbol_idx
    on public.research_watchpoints (user_id, symbol, enabled);

create table if not exists public.research_watchpoint_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    watchpoint_id uuid not null references public.research_watchpoints(id) on delete cascade,
    symbol text not null,
    event_type text not null default 'WATCHPOINT',
    message text not null,
    observed_value jsonb,
    triggered_at timestamptz not null
);

create index if not exists research_watchpoint_events_user_time_idx
    on public.research_watchpoint_events (user_id, triggered_at desc);

alter table public.research_snapshots enable row level security;
alter table public.research_provenance enable row level security;
alter table public.research_watchpoints enable row level security;
alter table public.research_watchpoint_events enable row level security;

revoke all on table public.research_snapshots, public.research_provenance, public.research_watchpoints, public.research_watchpoint_events from anon;
grant select, insert, update on table public.research_snapshots to authenticated;
grant select, insert on table public.research_provenance to authenticated;
grant select, insert, update, delete on table public.research_watchpoints to authenticated;
grant select on table public.research_watchpoint_events to authenticated;

drop policy if exists research_snapshots_own on public.research_snapshots;
create policy research_snapshots_own on public.research_snapshots for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists research_provenance_own on public.research_provenance;
create policy research_provenance_own on public.research_provenance for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists research_watchpoints_own on public.research_watchpoints;
create policy research_watchpoints_own on public.research_watchpoints for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists research_watchpoint_events_own on public.research_watchpoint_events;
create policy research_watchpoint_events_own on public.research_watchpoint_events for select to authenticated using ((select auth.uid()) = user_id);

create or replace function public.set_research_intelligence_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = timezone('utc', now()); return new; end;
$$;

drop trigger if exists research_watchpoints_set_updated_at on public.research_watchpoints;
create trigger research_watchpoints_set_updated_at before update on public.research_watchpoints for each row execute function public.set_research_intelligence_updated_at();
