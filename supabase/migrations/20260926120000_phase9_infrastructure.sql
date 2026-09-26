-- Phase 9: programmable research infrastructure, reproducibility and collaboration.

create schema if not exists private;

create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  key_prefix text not null unique,
  key_hash text not null unique,
  scopes text[] not null default array['market:read','research:read','signals:read','regimes:read','outcomes:read','analytics:read','runs:read','snapshots:read','exports:read'],
  active boolean not null default true,
  last_used_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  revoked_at timestamptz
);
create index if not exists api_keys_user_idx on public.api_keys(user_id, created_at desc);
create index if not exists api_keys_prefix_idx on public.api_keys(key_prefix);

create table if not exists public.webhook_endpoints (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  url text not null check (char_length(trim(url)) between 10 and 2048),
  events text[] not null default array['signal.event','regime.change','watchpoint.trigger','research.completed','outcome.event'],
  secret text not null,
  active boolean not null default true,
  failure_count integer not null default 0 check (failure_count >= 0),
  last_delivered_at timestamptz,
  last_error text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists webhook_endpoints_user_idx on public.webhook_endpoints(user_id, created_at desc);

create table if not exists public.webhook_deliveries (
  id uuid primary key default gen_random_uuid(),
  webhook_id uuid not null references public.webhook_endpoints(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'PENDING' check (status in ('PENDING','DELIVERED','FAILED')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  next_attempt_at timestamptz not null default timezone('utc', now()),
  delivered_at timestamptz,
  response_status integer,
  response_body text,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists webhook_deliveries_due_idx on public.webhook_deliveries(status, next_attempt_at);

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(trim(name)) between 1 and 120),
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists organizations_owner_idx on public.organizations(owner_user_id);

create table if not exists public.organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'viewer' check (role in ('owner','admin','editor','viewer')),
  created_at timestamptz not null default timezone('utc', now()),
  unique(organization_id,user_id)
);
create index if not exists organization_members_user_idx on public.organization_members(user_id, organization_id);

create table if not exists public.resource_shares (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  shared_by_user_id uuid not null references auth.users(id) on delete cascade,
  resource_type text not null check (resource_type in ('WORKSPACE','DASHBOARD','WATCHLIST','REPORT','RESEARCH_RUN','SNAPSHOT')),
  resource_id uuid not null,
  permission text not null default 'VIEW' check (permission in ('VIEW','EDIT','ADMIN')),
  created_at timestamptz not null default timezone('utc', now()),
  unique(organization_id,resource_type,resource_id)
);
create index if not exists resource_shares_org_idx on public.resource_shares(organization_id, resource_type, created_at desc);

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,
  action text not null,
  resource_type text,
  resource_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists audit_log_org_time_idx on public.audit_log(organization_id, created_at desc);

create table if not exists public.research_exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  export_type text not null check (export_type in ('JSON','CSV','SNAPSHOT','RUN','DATASET')),
  resource_type text not null,
  resource_id uuid,
  format text not null check (format in ('JSON','CSV')),
  dataset_version text not null,
  feature_version text not null,
  engine_version text not null,
  model_version text not null,
  row_count integer not null default 0,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists research_exports_user_time_idx on public.research_exports(user_id, created_at desc);

alter table public.research_snapshots
  add column if not exists research_run_id uuid references public.research_runs(id) on delete set null,
  add column if not exists dataset_version text not null default 'dataset-v1',
  add column if not exists feature_version text not null default 'features-v1',
  add column if not exists model_version text not null default 'deterministic-research',
  add column if not exists reproducibility_hash text;
create index if not exists research_snapshots_run_idx on public.research_snapshots(research_run_id);
create index if not exists research_snapshots_repro_idx on public.research_snapshots(user_id,reproducibility_hash);

alter table public.api_keys enable row level security;
alter table public.webhook_endpoints enable row level security;
alter table public.webhook_deliveries enable row level security;
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.resource_shares enable row level security;
alter table public.audit_log enable row level security;
alter table public.research_exports enable row level security;

revoke all on public.api_keys, public.webhook_endpoints, public.webhook_deliveries, public.organizations, public.organization_members, public.resource_shares, public.audit_log, public.research_exports from anon;
grant select,insert,update,delete on public.api_keys, public.webhook_endpoints, public.webhook_deliveries, public.organizations, public.organization_members, public.resource_shares, public.audit_log, public.research_exports to authenticated;
grant select,insert,update,delete on public.api_keys, public.webhook_endpoints, public.webhook_deliveries, public.organizations, public.organization_members, public.resource_shares, public.audit_log, public.research_exports to service_role;
grant select,insert,update on public.research_snapshots to service_role;

create or replace function private.user_is_org_member(p_org_id uuid)
returns boolean language sql stable security definer set search_path=''
as $$ select exists(select 1 from public.organization_members m where m.organization_id=p_org_id and m.user_id=(select auth.uid())); $$;
revoke execute on function private.user_is_org_member(uuid) from public,anon;
grant usage on schema private to authenticated;
grant execute on function private.user_is_org_member(uuid) to authenticated;

create policy api_keys_own on public.api_keys for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy webhook_endpoints_own on public.webhook_endpoints for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy webhook_deliveries_own on public.webhook_deliveries for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);

create policy organizations_member on public.organizations for select to authenticated using ((select auth.uid())=owner_user_id or (select private.user_is_org_member(id)));
create policy organizations_owner_insert on public.organizations for insert to authenticated with check ((select auth.uid())=owner_user_id);
create policy organizations_owner_update on public.organizations for update to authenticated using ((select auth.uid())=owner_user_id) with check ((select auth.uid())=owner_user_id);
create policy organizations_owner_delete on public.organizations for delete to authenticated using ((select auth.uid())=owner_user_id);

create policy organization_members_member on public.organization_members for select to authenticated using ((select auth.uid())=user_id or (select private.user_is_org_member(organization_id)));
create policy organization_members_owner_insert on public.organization_members for insert to authenticated with check (exists(select 1 from public.organizations o where o.id=organization_id and o.owner_user_id=(select auth.uid())));
create policy organization_members_owner_update on public.organization_members for update to authenticated using (exists(select 1 from public.organizations o where o.id=organization_id and o.owner_user_id=(select auth.uid()))) with check (exists(select 1 from public.organizations o where o.id=organization_id and o.owner_user_id=(select auth.uid())));
create policy organization_members_owner_delete on public.organization_members for delete to authenticated using (exists(select 1 from public.organizations o where o.id=organization_id and o.owner_user_id=(select auth.uid())));

create policy resource_shares_member on public.resource_shares for select to authenticated using ((select private.user_is_org_member(organization_id)));
create policy resource_shares_owner_insert on public.resource_shares for insert to authenticated with check ((select auth.uid())=shared_by_user_id and (select private.user_is_org_member(organization_id)));
create policy resource_shares_owner_delete on public.resource_shares for delete to authenticated using ((select auth.uid())=shared_by_user_id);
create policy audit_log_member on public.audit_log for select to authenticated using (actor_user_id=(select auth.uid()) or (organization_id is not null and (select private.user_is_org_member(organization_id))));
create policy research_exports_own on public.research_exports for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);

create or replace function public.consume_api_usage(p_user_id uuid,p_quantity bigint default 1)
returns table(allowed boolean,used bigint,limit_value bigint,period_start date,plan_id text)
language plpgsql security definer set search_path=''
as $$
declare v_period_start date:=date_trunc('month',timezone('utc',now()))::date; v_plan text:='free'; v_limit bigint:=0; v_used bigint:=0;
begin
 if p_quantity<=0 then raise exception 'Usage quantity must be positive'; end if;
 select bs.plan_id into v_plan from public.billing_subscriptions bs where bs.user_id=p_user_id and bs.status in ('trialing','active','past_due','unpaid','paused') and (bs.trial_ends_at is null or bs.trial_ends_at>timezone('utc',now())) order by bs.updated_at desc limit 1;
 v_plan:=coalesce(v_plan,'free');
 select coalesce(pl.limit_value,0) into v_limit from public.billing_plan_limits pl where pl.plan_id=v_plan and pl.metric='api_requests';
 v_limit:=coalesce(v_limit,0);
 insert into public.usage_counters(user_id,metric,period_start,used) values(p_user_id,'api_requests',v_period_start,0) on conflict(user_id,metric,period_start) do nothing;
 if v_limit=-1 then update public.usage_counters set used=used+p_quantity,updated_at=timezone('utc',now()) where user_id=p_user_id and metric='api_requests' and period_start=v_period_start returning used into v_used;
 else update public.usage_counters set used=used+p_quantity,updated_at=timezone('utc',now()) where user_id=p_user_id and metric='api_requests' and period_start=v_period_start and used+p_quantity<=v_limit returning used into v_used; end if;
 if v_used is null then select used into v_used from public.usage_counters where user_id=p_user_id and metric='api_requests' and period_start=v_period_start; return query select false,v_used,v_limit,v_period_start,v_plan; return; end if;
 insert into public.usage_events(user_id,metric,quantity,period_start,metadata) values(p_user_id,'api_requests',p_quantity,v_period_start,jsonb_build_object('source','phase9_api'));
 return query select true,v_used,v_limit,v_period_start,v_plan;
end; $$;
revoke execute on function public.consume_api_usage(uuid,bigint) from public,anon,authenticated;
grant execute on function public.consume_api_usage(uuid,bigint) to service_role;

insert into public.billing_features(id,name,description,category) values
 ('api','API access','Machine-readable research API access.','PLATFORM'),
 ('mcp','MCP access','Model Context Protocol access for research infrastructure.','PLATFORM'),
 ('webhooks','Webhooks','Programmatic event delivery.','AUTOMATION'),
 ('exports','Advanced exports','Expanded machine-readable research exports.','PLATFORM'),
 ('team_workspaces','Team workspaces','Shared research workspaces and collaboration.','COLLABORATION')
on conflict(id) do update set name=excluded.name,description=excluded.description,category=excluded.category;

create or replace function public.set_phase9_updated_at() returns trigger language plpgsql set search_path=''
as $$ begin new.updated_at=timezone('utc',now()); return new; end; $$;
revoke execute on function public.set_phase9_updated_at() from public,anon,authenticated;
drop trigger if exists webhook_endpoints_updated_at on public.webhook_endpoints;
create trigger webhook_endpoints_updated_at before update on public.webhook_endpoints for each row execute function public.set_phase9_updated_at();
drop trigger if exists organizations_updated_at on public.organizations;
create trigger organizations_updated_at before update on public.organizations for each row execute function public.set_phase9_updated_at();
