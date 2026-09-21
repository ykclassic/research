-- Phase 1: monetization, subscriptions, entitlements and usage.
create table if not exists public.billing_plans (
  id text primary key,
  name text not null,
  description text not null default '',
  monthly_price_minor bigint not null default 0 check (monthly_price_minor >= 0),
  currency text not null default 'USD' check (char_length(currency) = 3),
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.billing_features (
  id text primary key,
  name text not null,
  description text not null default '',
  category text not null check (category in ('CORE','INTELLIGENCE','QUANT','AUTOMATION','PLATFORM','COLLABORATION')),
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.billing_plan_features (
  plan_id text not null references public.billing_plans(id) on delete cascade,
  feature_id text not null references public.billing_features(id) on delete cascade,
  enabled boolean not null default true,
  primary key (plan_id, feature_id)
);

create table if not exists public.billing_plan_limits (
  plan_id text not null references public.billing_plans(id) on delete cascade,
  metric text not null,
  limit_value bigint not null check (limit_value = -1 or limit_value >= 0),
  reset_period text not null default 'monthly' check (reset_period = 'monthly'),
  primary key (plan_id, metric)
);

create table if not exists public.billing_subscriptions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  plan_id text not null references public.billing_plans(id),
  status text not null check (status in ('trialing','active','past_due','unpaid','paused','canceled','expired')),
  provider text not null default 'internal',
  provider_customer_id text,
  provider_subscription_id text,
  trial_started_at timestamptz,
  trial_ends_at timestamptz,
  current_period_start timestamptz,
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  canceled_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint billing_subscriptions_provider_ref_unique unique (provider, provider_subscription_id)
);

create unique index if not exists billing_subscriptions_one_live_per_user
  on public.billing_subscriptions(user_id)
  where status in ('trialing','active','past_due','unpaid','paused');

create table if not exists public.billing_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  provider_event_id text not null,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  processed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  unique(provider, provider_event_id)
);

create table if not exists public.usage_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  metric text not null,
  quantity bigint not null check (quantity > 0),
  period_start date not null,
  metadata jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.usage_counters (
  user_id uuid not null references auth.users(id) on delete cascade,
  metric text not null,
  period_start date not null,
  used bigint not null default 0 check (used >= 0),
  updated_at timestamptz not null default timezone('utc', now()),
  primary key (user_id, metric, period_start)
);

create index if not exists billing_subscriptions_user_idx on public.billing_subscriptions(user_id);
create index if not exists billing_events_user_idx on public.billing_events(user_id, created_at desc);
create index if not exists usage_events_user_idx on public.usage_events(user_id, occurred_at desc);
create index if not exists usage_counters_user_idx on public.usage_counters(user_id, period_start);

alter table public.billing_plans enable row level security;
alter table public.billing_features enable row level security;
alter table public.billing_plan_features enable row level security;
alter table public.billing_plan_limits enable row level security;
alter table public.billing_subscriptions enable row level security;
alter table public.billing_events enable row level security;
alter table public.usage_events enable row level security;
alter table public.usage_counters enable row level security;

drop policy if exists "authenticated can read active billing plans" on public.billing_plans;
create policy "authenticated can read active billing plans"
  on public.billing_plans for select to authenticated
  using (active = true);

drop policy if exists "authenticated can read billing features" on public.billing_features;
create policy "authenticated can read billing features"
  on public.billing_features for select to authenticated using (true);

drop policy if exists "authenticated can read plan features" on public.billing_plan_features;
create policy "authenticated can read plan features"
  on public.billing_plan_features for select to authenticated using (true);

drop policy if exists "authenticated can read plan limits" on public.billing_plan_limits;
create policy "authenticated can read plan limits"
  on public.billing_plan_limits for select to authenticated using (true);

drop policy if exists "users can read own subscription" on public.billing_subscriptions;
create policy "users can read own subscription"
  on public.billing_subscriptions for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "users can read own billing events" on public.billing_events;
create policy "users can read own billing events"
  on public.billing_events for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "users can read own usage events" on public.usage_events;
create policy "users can read own usage events"
  on public.usage_events for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "users can read own usage counters" on public.usage_counters;
create policy "users can read own usage counters"
  on public.usage_counters for select to authenticated
  using ((select auth.uid()) = user_id);

grant select on public.billing_plans, public.billing_features, public.billing_plan_features, public.billing_plan_limits to authenticated;
grant select on public.billing_subscriptions, public.billing_events, public.usage_events, public.usage_counters to authenticated;
grant select, insert, update on public.billing_subscriptions to service_role;
grant select, insert, update on public.billing_events to service_role;
grant select, insert, update on public.usage_events, public.usage_counters to service_role;

insert into public.billing_plans (id,name,description,monthly_price_minor,currency,display_order)
values
 ('free','Free','Explore and discover core market intelligence.',0,'USD',10),
 ('pro','Pro','Continuous research, monitoring and deeper intelligence.',0,'USD',20),
 ('premium','Premium / Professional','Research infrastructure, automation, API and collaboration.',0,'USD',30)
on conflict (id) do update set name=excluded.name, description=excluded.description, display_order=excluded.display_order, updated_at=timezone('utc', now());

insert into public.billing_features (id,name,description,category) values
 ('core_research','Core market research','Market data, technical analysis, regime and market structure.','CORE'),
 ('watchlists','Watchlists','Persistent personal watchlists.','CORE'),
 ('basic_portfolio','Basic portfolio intelligence','Basic positions and scenario analysis.','CORE'),
 ('signal_intelligence','Signal intelligence','Signal qualification and outcome audit.','INTELLIGENCE'),
 ('ai_research','AI research','Grounded AI research using verified application evidence.','INTELLIGENCE'),
 ('advanced_portfolio_analytics','Advanced portfolio analytics','Advanced exposure, correlation and risk analytics.','QUANT'),
 ('backtesting','Backtesting','Chronological strategy backtesting with costs and diagnostics.','QUANT'),
 ('strategy_builder','Strategy builder','Build and evaluate custom research strategies.','QUANT'),
 ('scanner','Intelligent scanner','Multi-condition market scanning and saved scans.','AUTOMATION'),
 ('webhooks','Webhooks','Programmatic event delivery.','AUTOMATION'),
 ('scheduled_workflows','Scheduled workflows','Scheduled research and monitoring workflows.','AUTOMATION'),
 ('api','API access','Machine-readable research API access.','PLATFORM'),
 ('mcp','MCP access','Model Context Protocol access for research infrastructure.','PLATFORM'),
 ('exports','Advanced exports','Expanded machine-readable research exports.','PLATFORM'),
 ('team_workspaces','Team workspaces','Shared research workspaces and collaboration.','COLLABORATION')
on conflict (id) do update set name=excluded.name, description=excluded.description, category=excluded.category;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
select 'free', id, id in ('core_research','watchlists','basic_portfolio','signal_intelligence','ai_research')
from public.billing_features
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
select 'pro', id, id in ('core_research','watchlists','basic_portfolio','signal_intelligence','ai_research','advanced_portfolio_analytics','backtesting','strategy_builder','scanner','scheduled_workflows','exports')
from public.billing_features
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
select 'premium', id, true
from public.billing_features
on conflict (plan_id,feature_id) do update set enabled=true;

insert into public.billing_plan_limits(plan_id,metric,limit_value)
values
 ('free','ai_research_runs',5),('free','scans',10),('free','exports',5),('free','api_requests',0),('free','historical_queries',20),('free','scheduled_workflows',0),
 ('pro','ai_research_runs',100),('pro','scans',500),('pro','exports',100),('pro','api_requests',10000),('pro','historical_queries',1000),('pro','scheduled_workflows',20),
 ('premium','ai_research_runs',500),('premium','scans',5000),('premium','exports',1000),('premium','api_requests',100000),('premium','historical_queries',10000),('premium','scheduled_workflows',100)
on conflict (plan_id,metric) do update set limit_value=excluded.limit_value;

create or replace function public.consume_usage(
  p_user_id uuid,
  p_metric text,
  p_quantity bigint default 1
)
returns table(allowed boolean, used bigint, limit_value bigint, period_start date, plan_id text)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_period_start date := date_trunc('month', timezone('utc', now()))::date;
  v_plan text := 'free';
  v_limit bigint := 0;
  v_used bigint := 0;
begin
  if (select auth.uid()) is null or (select auth.uid()) <> p_user_id then
    raise exception 'Unauthorized usage request';
  end if;
  if p_quantity <= 0 then
    raise exception 'Usage quantity must be positive';
  end if;

  select bs.plan_id into v_plan
  from public.billing_subscriptions bs
  where bs.user_id = p_user_id
    and bs.status in ('trialing','active','past_due','unpaid','paused')
    and (bs.trial_ends_at is null or bs.trial_ends_at > timezone('utc', now()))
  order by bs.updated_at desc
  limit 1;

  v_plan := coalesce(v_plan, 'free');

  select coalesce(pl.limit_value, 0) into v_limit
  from public.billing_plan_limits pl
  where pl.plan_id = v_plan and pl.metric = p_metric;

  v_limit := coalesce(v_limit, 0);

  insert into public.usage_counters(user_id, metric, period_start, used)
  values (p_user_id, p_metric, v_period_start, 0)
  on conflict (user_id, metric, period_start) do nothing;

  if v_limit = -1 then
    update public.usage_counters
      set used = used + p_quantity, updated_at = timezone('utc', now())
      where user_id = p_user_id and metric = p_metric and period_start = v_period_start
      returning used into v_used;
  else
    update public.usage_counters
      set used = used + p_quantity, updated_at = timezone('utc', now())
      where user_id = p_user_id and metric = p_metric and period_start = v_period_start
        and used + p_quantity <= v_limit
      returning used into v_used;
  end if;

  if v_used is null then
    select uc.used into v_used
    from public.usage_counters uc
    where uc.user_id = p_user_id and uc.metric = p_metric and uc.period_start = v_period_start;
    return query select false, v_used, v_limit, v_period_start, v_plan;
    return;
  end if;

  insert into public.usage_events(user_id, metric, quantity, period_start)
  values (p_user_id, p_metric, p_quantity, v_period_start);

  return query select true, v_used, v_limit, v_period_start, v_plan;
end;
$$;

revoke execute on function public.consume_usage(uuid,text,bigint) from public, anon;
grant execute on function public.consume_usage(uuid,text,bigint) to authenticated;

create or replace function public.start_pro_trial(p_user_id uuid, p_days integer default 14)
returns public.billing_subscriptions
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_row public.billing_subscriptions;
  v_start timestamptz := timezone('utc', now());
begin
  if (select auth.uid()) is null or (select auth.uid()) <> p_user_id then
    raise exception 'Unauthorized trial request';
  end if;
  if p_days < 1 or p_days > 30 then
    raise exception 'Trial duration must be between 1 and 30 days';
  end if;
  if exists (
    select 1 from public.billing_subscriptions
    where user_id=p_user_id and status in ('trialing','active','past_due','unpaid','paused')
  ) then
    raise exception 'An active subscription already exists';
  end if;

  insert into public.billing_subscriptions(
    user_id,plan_id,status,provider,trial_started_at,trial_ends_at,
    current_period_start,current_period_end
  )
  values (
    p_user_id,'pro','trialing','internal',v_start,v_start + make_interval(days => p_days),
    v_start,v_start + make_interval(days => p_days)
  )
  returning * into v_row;
  return v_row;
end;
$$;

revoke execute on function public.start_pro_trial(uuid,integer) from public, anon;
grant execute on function public.start_pro_trial(uuid,integer) to authenticated;
