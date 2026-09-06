create table if not exists public.alert_rules (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    symbol text not null,
    condition_type text not null check (condition_type in ('RSI_THRESHOLD','PRICE_CROSS','REGIME_CHANGE','BULLISH_BOS')),
    operator text,
    threshold numeric,
    timeframe text not null default '1h',
    enabled boolean not null default true,
    cooldown_minutes integer not null default 60 check (cooldown_minutes between 0 and 10080),
    channels jsonb not null default '["WEB"]'::jsonb,
    state jsonb not null default '{}'::jsonb,
    last_triggered_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint alert_rules_rsi_fields check (
        condition_type <> 'RSI_THRESHOLD' or (operator in ('LT','LTE','GT','GTE') and threshold between 0 and 100)
    ),
    constraint alert_rules_price_fields check (
        condition_type <> 'PRICE_CROSS' or (operator in ('ABOVE','BELOW') and threshold > 0)
    ),
    constraint alert_rules_non_numeric_fields check (
        condition_type not in ('REGIME_CHANGE','BULLISH_BOS') or (operator is null and threshold is null)
    )
);

create index if not exists alert_rules_user_enabled_idx on public.alert_rules(user_id, enabled, created_at desc);
create index if not exists alert_rules_user_symbol_idx on public.alert_rules(user_id, symbol, enabled);

create table if not exists public.alert_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    rule_id uuid not null references public.alert_rules(id) on delete cascade,
    symbol text not null,
    condition_type text not null,
    title text not null,
    message text not null,
    payload jsonb not null default '{}'::jsonb,
    channels jsonb not null default '["WEB"]'::jsonb,
    triggered_at timestamptz not null default now(),
    read_at timestamptz,
    fingerprint text not null,
    created_at timestamptz not null default now(),
    constraint alert_events_fingerprint_unique unique(rule_id, fingerprint)
);

create index if not exists alert_events_user_unread_idx on public.alert_events(user_id, read_at, triggered_at desc);
create index if not exists alert_events_user_triggered_idx on public.alert_events(user_id, triggered_at desc);

create or replace function public.set_alerts_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists alert_rules_set_updated_at on public.alert_rules;
create trigger alert_rules_set_updated_at
before update on public.alert_rules
for each row execute function public.set_alerts_updated_at();

grant select, insert, update, delete on public.alert_rules to authenticated;
grant select, insert, update, delete on public.alert_events to authenticated;

alter table public.alert_rules enable row level security;
alter table public.alert_events enable row level security;

drop policy if exists alert_rules_select_own on public.alert_rules;
create policy alert_rules_select_own on public.alert_rules for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists alert_rules_insert_own on public.alert_rules;
create policy alert_rules_insert_own on public.alert_rules for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists alert_rules_update_own on public.alert_rules;
create policy alert_rules_update_own on public.alert_rules for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists alert_rules_delete_own on public.alert_rules;
create policy alert_rules_delete_own on public.alert_rules for delete to authenticated using ((select auth.uid()) = user_id);

drop policy if exists alert_events_select_own on public.alert_events;
create policy alert_events_select_own on public.alert_events for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists alert_events_insert_own on public.alert_events;
create policy alert_events_insert_own on public.alert_events for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists alert_events_update_own on public.alert_events;
create policy alert_events_update_own on public.alert_events for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

drop policy if exists alert_events_delete_own on public.alert_events;
create policy alert_events_delete_own on public.alert_events for delete to authenticated using ((select auth.uid()) = user_id);
