-- Monetization phase 1 lifecycle, usage notifications and workflow/API metering support.
create table if not exists public.billing_usage_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  metric text not null,
  period_start date not null,
  threshold_percent integer not null check (threshold_percent in (80,90,100)),
  used bigint not null,
  limit_value bigint not null,
  created_at timestamptz not null default timezone('utc', now()),
  unique(user_id, metric, period_start, threshold_percent)
);

alter table public.billing_usage_notifications enable row level security;
drop policy if exists "users can read own usage notifications" on public.billing_usage_notifications;
create policy "users can read own usage notifications"
  on public.billing_usage_notifications for select to authenticated
  using ((select auth.uid()) = user_id);
grant select on public.billing_usage_notifications to authenticated;
grant select, insert on public.billing_usage_notifications to service_role;

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
  v_threshold integer;
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
    update public.usage_counters set used = used + p_quantity, updated_at = timezone('utc', now())
      where user_id=p_user_id and metric=p_metric and period_start=v_period_start
      returning used into v_used;
  else
    update public.usage_counters set used = used + p_quantity, updated_at = timezone('utc', now())
      where user_id=p_user_id and metric=p_metric and period_start=v_period_start and used + p_quantity <= v_limit
      returning used into v_used;
  end if;

  if v_used is null then
    select uc.used into v_used from public.usage_counters uc
      where uc.user_id=p_user_id and uc.metric=p_metric and uc.period_start=v_period_start;
    return query select false, v_used, v_limit, v_period_start, v_plan;
    return;
  end if;

  insert into public.usage_events(user_id, metric, quantity, period_start)
    values (p_user_id, p_metric, p_quantity, v_period_start);

  if v_limit > 0 then
    foreach v_threshold in array[80,90,100] loop
      if v_used * 100 >= v_limit * v_threshold then
        insert into public.billing_usage_notifications(user_id,metric,period_start,threshold_percent,used,limit_value)
          values (p_user_id,p_metric,v_period_start,v_threshold,v_used,v_limit)
          on conflict (user_id,metric,period_start,threshold_percent) do nothing;
      end if;
    end loop;
  end if;

  return query select true, v_used, v_limit, v_period_start, v_plan;
end;
$$;

revoke execute on function public.consume_usage(uuid,text,bigint) from public, anon;
grant execute on function public.consume_usage(uuid,text,bigint) to authenticated;
