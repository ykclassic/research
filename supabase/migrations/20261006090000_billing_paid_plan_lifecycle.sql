-- Billing lifecycle: paid entitlements expire at the Stripe subscription period end.
-- The application treats current_period_end as the entitlement boundary and the
-- Stripe subscription is configured to cancel at that boundary after Checkout.
--
-- Keep the database-side usage guard aligned with the application entitlement
-- resolver so expired paid subscriptions cannot retain paid usage limits.

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
    and (
      (bs.status = 'trialing' and (bs.trial_ends_at is null or bs.trial_ends_at > timezone('utc', now())))
      or
      (bs.status <> 'trialing' and (bs.current_period_end is null or bs.current_period_end > timezone('utc', now())))
    )
  order by bs.updated_at desc
  limit 1;

  v_plan := coalesce(v_plan, 'free');

  select coalesce(pl.limit_value,0) into v_limit
  from public.billing_plan_limits pl
  where pl.plan_id = v_plan and pl.metric = p_metric;

  v_limit := coalesce(v_limit,0);

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
