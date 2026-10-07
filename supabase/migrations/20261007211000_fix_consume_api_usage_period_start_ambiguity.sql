-- Fix the remaining usage RPC ambiguity caused by the OUT parameter period_start.
-- Keep the public return contract unchanged while qualifying every table reference.

create or replace function public.consume_api_usage(p_user_id uuid,p_quantity bigint default 1)
returns table(allowed boolean,used bigint,limit_value bigint,period_start date,plan_id text)
language plpgsql security definer set search_path=''
as $$
declare
  v_period_start date := date_trunc('month', timezone('utc', now()))::date;
  v_plan text := 'free';
  v_limit bigint := 0;
  v_used bigint := 0;
begin
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
  where pl.plan_id = v_plan
    and pl.metric = 'api_requests';

  v_limit := coalesce(v_limit, 0);

  insert into public.usage_counters(user_id, metric, period_start, used)
  values (p_user_id, 'api_requests', v_period_start, 0)
  on conflict (user_id, metric, period_start) do nothing;

  if v_limit = -1 then
    update public.usage_counters uc
      set used = uc.used + p_quantity,
          updated_at = timezone('utc', now())
      where uc.user_id = p_user_id
        and uc.metric = 'api_requests'
        and uc.period_start = v_period_start
      returning uc.used into v_used;
  else
    update public.usage_counters uc
      set used = uc.used + p_quantity,
          updated_at = timezone('utc', now())
      where uc.user_id = p_user_id
        and uc.metric = 'api_requests'
        and uc.period_start = v_period_start
        and uc.used + p_quantity <= v_limit
      returning uc.used into v_used;
  end if;

  if v_used is null then
    select uc.used into v_used
    from public.usage_counters uc
    where uc.user_id = p_user_id
      and uc.metric = 'api_requests'
      and uc.period_start = v_period_start;
    return query select false, v_used, v_limit, v_period_start, v_plan;
    return;
  end if;

  insert into public.usage_events(user_id, metric, quantity, period_start, metadata)
  values (p_user_id, 'api_requests', p_quantity, v_period_start, jsonb_build_object('source','phase9_api'));

  return query select true, v_used, v_limit, v_period_start, v_plan;
end;
$$;

revoke execute on function public.consume_api_usage(uuid,bigint) from public,anon,authenticated;
grant execute on function public.consume_api_usage(uuid,bigint) to service_role;
