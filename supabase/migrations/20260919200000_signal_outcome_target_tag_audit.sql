-- Phase 5: immutable Signal Outcome & Target-Tag Audit.
-- A signal enters this table only after the user clicks "Log Signal".
-- Every row is immutable. Outcome changes are represented by a new revision.
-- This preserves the original signal snapshot and creates an auditable chronology.

create table if not exists public.signal_outcome_audit (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    signal_id uuid not null,
    revision integer not null check (revision >= 1),

    symbol text not null,
    signal text not null check (signal in ('BUY','STRONG_BUY','SELL','STRONG_SELL')),
    score numeric(12,10) not null check (score between -1 and 1),
    confidence numeric(12,10) not null check (confidence between 0 and 1),

    dispatched_at timestamptz not null,
    entry_price numeric(30,12) not null check (entry_price > 0),
    stop_loss numeric(30,12) not null check (stop_loss > 0),
    target_price numeric(30,12) not null check (target_price > 0),

    target_tagged_at timestamptz,
    stop_tagged_at timestamptz,
    target_tag_latency_seconds double precision check (
        target_tag_latency_seconds is null or target_tag_latency_seconds >= 0
    ),
    stop_tag_latency_seconds double precision check (
        stop_tag_latency_seconds is null or stop_tag_latency_seconds >= 0
    ),

    first_touch_price numeric(30,12),
    first_touch_timestamp timestamptz,
    outcome text not null check (
        outcome in ('PENDING','TARGET_HIT','STOP_LOSS_HIT','AMBIGUOUS')
    ),

    provider text not null,
    timeframe text not null,
    signal_engine_version text not null,

    calculated_at timestamptz not null,
    latest_candle_timestamp timestamptz not null,
    observed_at timestamptz not null,
    observation_candle_timestamp timestamptz,
    observation_source text,
    coverage_warning text,
    created_at timestamptz not null default timezone('utc', now()),

    constraint signal_outcome_audit_signal_revision_unique
        unique (signal_id, revision),
    constraint signal_outcome_audit_dispatch_after_calculation
        check (dispatched_at >= calculated_at),
    constraint signal_outcome_audit_first_touch_consistency
        check (
            first_touch_timestamp is null
            or first_touch_timestamp >= dispatched_at
        )
);

create index if not exists signal_outcome_audit_user_created_idx
    on public.signal_outcome_audit (user_id, created_at desc);

create index if not exists signal_outcome_audit_signal_revision_idx
    on public.signal_outcome_audit (signal_id, revision desc);

alter table public.signal_outcome_audit enable row level security;

revoke all on table public.signal_outcome_audit from anon, authenticated;
grant select, insert on table public.signal_outcome_audit to authenticated;

drop policy if exists "signal_outcome_audit_select_own"
    on public.signal_outcome_audit;
drop policy if exists "signal_outcome_audit_insert_own"
    on public.signal_outcome_audit;

create policy "signal_outcome_audit_select_own"
    on public.signal_outcome_audit
    for select
    to authenticated
    using ((select auth.uid()) = user_id);

create policy "signal_outcome_audit_insert_own"
    on public.signal_outcome_audit
    for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

create or replace function public.reject_signal_outcome_audit_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'Signal Outcome & Target-Tag Audit records are immutable.';
end;
$$;

drop trigger if exists signal_outcome_audit_immutable
    on public.signal_outcome_audit;

create trigger signal_outcome_audit_immutable
before update or delete
on public.signal_outcome_audit
for each row
execute function public.reject_signal_outcome_audit_mutation();
