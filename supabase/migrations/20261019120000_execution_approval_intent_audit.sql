-- Phase 1 execution persistence contract.
-- This migration is repository-only; execution remains disabled.
create schema if not exists extensions;
create extension if not exists pgcrypto with schema extensions;
do $role$
begin
  create role execution_persistence_owner nologin nosuperuser nocreatedb nocreaterole noinherit;
exception when duplicate_object then
  alter role execution_persistence_owner nologin nosuperuser nocreatedb nocreaterole noinherit;
end
$role$;
revoke create on schema public from public, anon, authenticated;
-- Repository-only migration. Do not apply to production during Phase 1.
-- Browser roles have no direct table grants or RLS policies; all writes use
-- narrow service-role RPCs that run atomically under the migration owner.

create table if not exists public.execution_intents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  idempotency_key text not null check (char_length(idempotency_key) between 16 and 128),
  request_hash text not null check (request_hash ~ '^[a-f0-9]{64}$'),
  signal_snapshot jsonb not null check (jsonb_typeof(signal_snapshot) = 'object'),
  account_snapshot jsonb not null check (jsonb_typeof(account_snapshot) = 'object'),
  market_snapshot jsonb not null check (jsonb_typeof(market_snapshot) = 'object'),
  risk_snapshot jsonb not null check (jsonb_typeof(risk_snapshot) = 'object'),
  status text not null default 'AWAITING_APPROVAL'
    check (status in ('AWAITING_APPROVAL','APPROVED','REJECTED','EXPIRED','EXECUTING','EXECUTED','FAILED','UNKNOWN','CANCELLED')),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key),
  check (expires_at > created_at)
);

create index if not exists execution_intents_user_status_idx
  on public.execution_intents(user_id, status, created_at desc);

create table if not exists public.execution_approvals (
  id uuid primary key default gen_random_uuid(),
  intent_id uuid not null unique references public.execution_intents(id) on delete restrict,
  user_id uuid not null references auth.users(id) on delete restrict,
  actor_user_id uuid not null references auth.users(id) on delete restrict,
  decision text not null check (decision in ('APPROVE','REJECT')),
  approved_at timestamptz not null default now(),
  expires_at timestamptz not null,
  approval_snapshot jsonb not null check (jsonb_typeof(approval_snapshot) = 'object'),
  snapshot_hash text not null check (snapshot_hash ~ '^[a-f0-9]{64}$'),
  check (expires_at > approved_at)
);

create table if not exists public.execution_records (
  id uuid primary key default gen_random_uuid(),
  intent_id uuid not null unique references public.execution_intents(id) on delete restrict,
  approval_id uuid not null unique references public.execution_approvals(id) on delete restrict,
  user_id uuid not null references auth.users(id) on delete restrict,
  idempotency_key text not null unique check (char_length(idempotency_key) between 16 and 128),
  result_status text not null check (result_status in ('FILLED','FAILED','REJECTED','UNKNOWN')),
  broker_order_id text,
  result_snapshot jsonb not null check (jsonb_typeof(result_snapshot) = 'object'),
  recorded_at timestamptz not null default now()
);

create table if not exists public.execution_events (
  event_seq bigint generated always as identity primary key,
  intent_id uuid not null references public.execution_intents(id) on delete restrict,
  user_id uuid not null references auth.users(id) on delete restrict,
  actor_user_id uuid references auth.users(id) on delete restrict,
  event_type text not null check (event_type in (
    'INTENT_CREATED','APPROVAL_ACCEPTED','APPROVAL_REJECTED',
    'EXECUTION_CLAIMED','EXECUTION_RECORDED','EXECUTION_UNKNOWN',
    'INTENT_EXPIRED','INTENT_CANCELLED'
  )),
  event_data jsonb not null default '{}'::jsonb check (jsonb_typeof(event_data) = 'object'),
  occurred_at timestamptz not null default now()
);

create index if not exists execution_events_intent_seq_idx
  on public.execution_events(intent_id, event_seq);

create or replace function public.execution_snapshot_sha256(p_snapshot jsonb)
returns text
language sql
immutable
strict
security definer
set search_path = pg_catalog
as $snapshot_hash$
  select pg_catalog.encode(
    extensions.digest(pg_catalog.convert_to(p_snapshot::text, 'UTF8'), 'sha256'),
    'hex'
  );
$snapshot_hash$;

create or replace function public.execution_intent_request_sha256(
  p_signal_snapshot jsonb,
  p_account_snapshot jsonb,
  p_market_snapshot jsonb,
  p_risk_snapshot jsonb
)
returns text
language sql
immutable
strict
security definer
set search_path = pg_catalog
as $intent_hash$
  select public.execution_snapshot_sha256(pg_catalog.jsonb_build_object(
    'signal_snapshot', p_signal_snapshot,
    'account_snapshot', p_account_snapshot,
    'market_snapshot', p_market_snapshot,
    'risk_snapshot', p_risk_snapshot
  ));
$intent_hash$;

alter table public.execution_intents enable row level security;
alter table public.execution_approvals enable row level security;
alter table public.execution_records enable row level security;
alter table public.execution_events enable row level security;

revoke all on public.execution_intents, public.execution_approvals,
  public.execution_records, public.execution_events from public, anon, authenticated, service_role;

create or replace function public.reject_execution_record_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  raise exception 'execution evidence is append-only' using errcode = '55000';
end;
$$;

drop trigger if exists execution_approvals_immutable on public.execution_approvals;
create trigger execution_approvals_immutable
before update or delete on public.execution_approvals
for each row execute function public.reject_execution_record_mutation();

drop trigger if exists execution_records_immutable on public.execution_records;
create trigger execution_records_immutable
before update or delete on public.execution_records
for each row execute function public.reject_execution_record_mutation();

drop trigger if exists execution_events_immutable on public.execution_events;
create trigger execution_events_immutable
before update or delete on public.execution_events
for each row execute function public.reject_execution_record_mutation();

create or replace function public.guard_execution_intent_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog
as $intent_guard$
begin
  if tg_op = 'DELETE' then
    raise exception 'execution intents cannot be deleted' using errcode = '55000';
  end if;

  if (to_jsonb(new) - 'status' - 'updated_at')
       is distinct from
     (to_jsonb(old) - 'status' - 'updated_at') then
    raise exception 'execution intent payload is immutable' using errcode = '55000';
  end if;

  if new.status is distinct from old.status then
    if pg_catalog.current_setting('app.execution_transition', true) is distinct from 'approval'
       and pg_catalog.current_setting('app.execution_transition', true) is distinct from 'result' then
      raise exception 'execution intent state may only change through a persistence RPC' using errcode = '55000';
    end if;
    if not (
      (old.status = 'AWAITING_APPROVAL' and new.status in ('APPROVED', 'REJECTED'))
      or (old.status = 'EXECUTING' and new.status in ('EXECUTED', 'FAILED', 'UNKNOWN'))
    ) then
      raise exception 'invalid execution intent state transition' using errcode = '55000';
    end if;
  elsif new.updated_at is distinct from old.updated_at then
    raise exception 'execution intent timestamp cannot change without a state transition' using errcode = '55000';
  end if;

  return new;
end;
$intent_guard$;

drop trigger if exists execution_intents_transition_guard on public.execution_intents;
create trigger execution_intents_transition_guard
before update or delete on public.execution_intents
for each row execute function public.guard_execution_intent_mutation();

create or replace function public.create_execution_intent(
  p_user_id uuid,
  p_idempotency_key text,
  p_request_hash text,
  p_signal_snapshot jsonb,
  p_account_snapshot jsonb,
  p_market_snapshot jsonb,
  p_risk_snapshot jsonb,
  p_expires_at timestamptz
)
returns table(intent_id uuid, created boolean)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_id uuid;
  v_created boolean := false;
  v_expected_request_hash text;
begin
  if jsonb_typeof(p_signal_snapshot) is distinct from 'object'
     or jsonb_typeof(p_account_snapshot) is distinct from 'object'
     or jsonb_typeof(p_market_snapshot) is distinct from 'object'
     or jsonb_typeof(p_risk_snapshot) is distinct from 'object' then
    raise exception 'execution snapshots must be JSON objects' using errcode = '22023';
  end if;
  v_expected_request_hash := public.execution_intent_request_sha256(
    p_signal_snapshot, p_account_snapshot, p_market_snapshot, p_risk_snapshot
  );
  if p_request_hash is distinct from v_expected_request_hash then
    raise exception 'request hash does not match canonical intent snapshots' using errcode = '22023';
  end if;
  if p_expires_at <= now() then
    raise exception 'intent expiry must be in the future' using errcode = '22023';
  end if;

  insert into public.execution_intents(
    user_id, idempotency_key, request_hash, signal_snapshot,
    account_snapshot, market_snapshot, risk_snapshot, expires_at
  ) values (
    p_user_id, p_idempotency_key, p_request_hash, p_signal_snapshot,
    p_account_snapshot, p_market_snapshot, p_risk_snapshot, p_expires_at
  )
  on conflict (user_id, idempotency_key) do nothing
  returning id into v_id;

  if v_id is not null then
    v_created := true;
    insert into public.execution_events(intent_id, user_id, event_type, event_data)
    values (v_id, p_user_id, 'INTENT_CREATED',
      jsonb_build_object('request_hash', p_request_hash));
  else
    select i.id, (i.request_hash = p_request_hash)
      into v_id, v_created
      from public.execution_intents i
      where i.user_id = p_user_id and i.idempotency_key = p_idempotency_key;
    if v_id is null then
      raise exception 'idempotency conflict could not be resolved' using errcode = '40001';
    end if;
    if not v_created then
      raise exception 'idempotency key reused with different request' using errcode = '23505';
    end if;
    v_created := false;
  end if;

  return query select v_id, v_created;
end;
$$;

create or replace function public.record_execution_approval(
  p_user_id uuid,
  p_intent_id uuid,
  p_decision text,
  p_actor_user_id uuid,
  p_approval_snapshot jsonb,
  p_snapshot_hash text,
  p_expires_at timestamptz
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_intent public.execution_intents%rowtype;
  v_approval_id uuid;
  v_now timestamptz := now();
  v_expected_approval_snapshot jsonb;
begin
  if p_decision not in ('APPROVE','REJECT') then
    raise exception 'invalid approval decision' using errcode = '22023';
  end if;

  select * into v_intent
    from public.execution_intents i
    where i.id = p_intent_id and i.user_id = p_user_id
    for update;

  if not found or v_intent.status <> 'AWAITING_APPROVAL' or v_intent.expires_at <= v_now then
    raise exception 'intent is missing, expired, or not awaiting approval' using errcode = '55000';
  end if;
  if p_actor_user_id <> p_user_id then
    raise exception 'approval actor does not own intent' using errcode = '42501';
  end if;
  if p_expires_at <= v_now or p_expires_at > v_intent.expires_at then
    raise exception 'approval expiry is invalid' using errcode = '22023';
  end if;
  v_expected_approval_snapshot := pg_catalog.jsonb_build_object(
    'intent_id', v_intent.id,
    'request_hash', v_intent.request_hash,
    'account_ref', v_intent.account_snapshot -> 'account_ref',
    'symbol', v_intent.signal_snapshot -> 'symbol',
    'side', v_intent.signal_snapshot -> 'side',
    'quantity', v_intent.signal_snapshot -> 'quantity',
    'entry_price', v_intent.signal_snapshot -> 'entry_price',
    'stop_loss', v_intent.signal_snapshot -> 'stop_loss',
    'take_profit', v_intent.signal_snapshot -> 'take_profit',
    'risk_policy_version', v_intent.risk_snapshot -> 'risk_policy_version',
    'human_confirmed', 'true'::jsonb
  );
  if p_approval_snapshot is distinct from v_expected_approval_snapshot
     or p_snapshot_hash is distinct from public.execution_snapshot_sha256(p_approval_snapshot) then
    raise exception 'approval snapshot does not match canonical approved intent' using errcode = '22023';
  end if;

  insert into public.execution_approvals(
    intent_id, user_id, actor_user_id, decision, expires_at,
    approval_snapshot, snapshot_hash
  ) values (
    p_intent_id, p_user_id, p_actor_user_id, p_decision, p_expires_at,
    p_approval_snapshot, p_snapshot_hash
  ) returning id into v_approval_id;

  perform pg_catalog.set_config('app.execution_transition', 'approval', true);
  update public.execution_intents
    set status = case when p_decision = 'APPROVE' then 'APPROVED' else 'REJECTED' end,
        updated_at = v_now
    where id = p_intent_id;

  insert into public.execution_events(intent_id, user_id, actor_user_id, event_type, event_data)
  values (
    p_intent_id, p_user_id, p_actor_user_id,
    case when p_decision = 'APPROVE' then 'APPROVAL_ACCEPTED' else 'APPROVAL_REJECTED' end,
    jsonb_build_object('approval_id', v_approval_id, 'snapshot_hash', p_snapshot_hash, 'expires_at', p_expires_at)
  );

  return v_approval_id;
end;
$$;

create or replace function public.claim_execution(
  p_user_id uuid,
  p_intent_id uuid,
  p_approval_id uuid,
  p_revalidation_snapshot jsonb,
  p_revalidation_hash text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
  -- Deliberate hard stop: caller-supplied JSON and a self-computed hash do not
  -- prove authoritative provider provenance. A separately reviewed server-side
  -- orchestration contract must replace this guard before any claim is enabled.
  raise exception 'execution is disabled until trusted revalidation provenance is integrated'
    using errcode = '55000';
end;
$$;

create or replace function public.record_execution_result(
  p_user_id uuid,
  p_intent_id uuid,
  p_approval_id uuid,
  p_idempotency_key text,
  p_result_status text,
  p_broker_order_id text,
  p_result_snapshot jsonb
)
returns uuid
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
  raise exception 'execution is disabled; execution results cannot be recorded without an authorized claim'
    using errcode = '55000';
end;
$$;

grant usage on schema public to execution_persistence_owner;
grant usage on schema extensions to execution_persistence_owner;
grant create on schema public to execution_persistence_owner;
alter table public.execution_intents owner to execution_persistence_owner;
alter table public.execution_approvals owner to execution_persistence_owner;
alter table public.execution_records owner to execution_persistence_owner;
alter table public.execution_events owner to execution_persistence_owner;
alter function public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz) owner to execution_persistence_owner;
alter function public.record_execution_approval(uuid,uuid,text,uuid,jsonb,text,timestamptz) owner to execution_persistence_owner;
alter function public.claim_execution(uuid,uuid,uuid,jsonb,text) owner to execution_persistence_owner;
alter function public.record_execution_result(uuid,uuid,uuid,text,text,text,jsonb) owner to execution_persistence_owner;
alter function public.execution_snapshot_sha256(jsonb) owner to execution_persistence_owner;
alter function public.execution_intent_request_sha256(jsonb,jsonb,jsonb,jsonb) owner to execution_persistence_owner;
grant select, insert, update on public.execution_intents, public.execution_approvals, public.execution_records, public.execution_events to execution_persistence_owner;
grant usage, select on sequence public.execution_events_event_seq_seq to execution_persistence_owner;
revoke create on schema public from execution_persistence_owner;
revoke all on function public.execution_snapshot_sha256(jsonb) from public, anon, authenticated;
revoke all on function public.execution_intent_request_sha256(jsonb,jsonb,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.execution_snapshot_sha256(jsonb) to execution_persistence_owner;
grant execute on function public.execution_intent_request_sha256(jsonb,jsonb,jsonb,jsonb) to execution_persistence_owner;
grant execute on function public.execution_snapshot_sha256(jsonb) to service_role;
grant execute on function public.execution_intent_request_sha256(jsonb,jsonb,jsonb,jsonb) to service_role;
revoke all on function public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz) from public, anon, authenticated;
revoke all on function public.record_execution_approval(uuid,uuid,text,uuid,jsonb,text,timestamptz) from public, anon, authenticated;
revoke all on function public.claim_execution(uuid,uuid,uuid,jsonb,text) from public, anon, authenticated;
revoke all on function public.record_execution_result(uuid,uuid,uuid,text,text,text,jsonb) from public, anon, authenticated;
grant execute on function public.create_execution_intent(uuid,text,text,jsonb,jsonb,jsonb,jsonb,timestamptz) to service_role;
grant execute on function public.record_execution_approval(uuid,uuid,text,uuid,jsonb,text,timestamptz) to service_role;
grant execute on function public.claim_execution(uuid,uuid,uuid,jsonb,text) to service_role;
grant execute on function public.record_execution_result(uuid,uuid,uuid,text,text,text,jsonb) to service_role;
