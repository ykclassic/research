-- Phase 5: user-initiated Signal Outcome & Target-Tag Audit.
-- A signal enters this audit only after the user clicks "Log Signal".
-- signal_audit_records is immutable: it is the original signal snapshot.
-- signal_audit_outcomes is append-only and records the first terminal observation.
-- Target/stop timestamps are candle-observation timestamps because OHLC data cannot
-- establish the exact intrabar second. If target and stop are both touched in the
-- same completed candle, the outcome is AMBIGUOUS rather than inventing an order.

create table if not exists public.signal_audit_records (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    signal_id uuid not null unique,
    symbol text not null,
    signal text not null check (signal in ('BUY','STRONG_BUY','SELL','STRONG_SELL','NEUTRAL')),
    score numeric(12,10) not null check (score between -1 and 1),
    confidence numeric(12,10) not null check (confidence between 0 and 1),
    dispatched_at timestamptz not null,
    entry_price numeric(30,12) not null check (entry_price > 0),
    stop_loss numeric(30,12) check (stop_loss is null or stop_loss > 0),
    target_price numeric(30,12) check (target_price is null or target_price > 0),
    provider text not null,
    timeframe text not null check (timeframe in ('15m')),
    signal_engine_version text not null,
    calculated_at timestamptz not null,
    latest_candle_timestamp timestamptz not null,
    created_at timestamptz not null default timezone('utc', now()),
    constraint signal_audit_dispatch_after_calculation check (dispatched_at >= calculated_at)
);

create index if not exists signal_audit_records_user_created_idx
    on public.signal_audit_records (user_id, created_at desc);
create index if not exists signal_audit_records_user_symbol_idx
    on public.signal_audit_records (user_id, symbol, created_at desc);

create table if not exists public.signal_audit_outcomes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    signal_id uuid not null unique references public.signal_audit_records(signal_id) on delete cascade,
    target_tagged_at timestamptz,
    stop_tagged_at timestamptz,
    target_tag_latency_seconds double precision check (target_tag_latency_seconds is null or target_tag_latency_seconds >= 0),
    stop_tag_latency_seconds double precision check (stop_tag_latency_seconds is null or stop_tag_latency_seconds >= 0),
    first_touch_price numeric(30,12) check (first_touch_price is null or first_touch_price > 0),
    first_touch_timestamp timestamptz,
    outcome text not null check (outcome in ('TARGET_HIT','STOP_LOSS_HIT','AMBIGUOUS')),
    observed_at timestamptz not null default timezone('utc', now()),
    observation_candle_timestamp timestamptz,
    observation_source text,
    coverage_warning text,
    created_at timestamptz not null default timezone('utc', now())
);

create index if not exists signal_audit_outcomes_user_created_idx
    on public.signal_audit_outcomes (user_id, created_at desc);

alter table public.signal_audit_records enable row level security;
alter table public.signal_audit_outcomes enable row level security;

revoke all on table public.signal_audit_records from anon, authenticated;
revoke all on table public.signal_audit_outcomes from anon, authenticated;
grant select, insert on table public.signal_audit_records to authenticated;
grant select, insert on table public.signal_audit_outcomes to authenticated;

drop policy if exists "signal_audit_records_select_own" on public.signal_audit_records;
drop policy if exists "signal_audit_records_insert_own" on public.signal_audit_records;
drop policy if exists "signal_audit_outcomes_select_own" on public.signal_audit_outcomes;
drop policy if exists "signal_audit_outcomes_insert_own" on public.signal_audit_outcomes;

create policy "signal_audit_records_select_own"
    on public.signal_audit_records for select to authenticated
    using ((select auth.uid()) = user_id);
create policy "signal_audit_records_insert_own"
    on public.signal_audit_records for insert to authenticated
    with check ((select auth.uid()) = user_id);

create policy "signal_audit_outcomes_select_own"
    on public.signal_audit_outcomes for select to authenticated
    using ((select auth.uid()) = user_id);
create policy "signal_audit_outcomes_insert_own"
    on public.signal_audit_outcomes for insert to authenticated
    with check (
        (select auth.uid()) = user_id
        and exists (
            select 1 from public.signal_audit_records r
            where r.signal_id = signal_audit_outcomes.signal_id
              and r.user_id = (select auth.uid())
        )
    );

create or replace function public.reject_signal_audit_record_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'Signal audit records are immutable; create a new audit record instead.';
end;
$$;

drop trigger if exists signal_audit_records_immutable on public.signal_audit_records;
create trigger signal_audit_records_immutable
before update or delete on public.signal_audit_records
for each row execute function public.reject_signal_audit_record_mutation();

drop trigger if exists signal_audit_outcomes_immutable on public.signal_audit_outcomes;
create trigger signal_audit_outcomes_immutable
before update or delete on public.signal_audit_outcomes
for each row execute function public.reject_signal_audit_record_mutation();
