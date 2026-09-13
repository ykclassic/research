-- Settings foundation: user-scoped research preferences with RLS.
-- The seven JSONB preference groups are kept together so one PUT is one
-- Postgres row operation and therefore updates the user's settings atomically.

create table if not exists public.user_preferences (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null unique references auth.users(id) on delete cascade,
    research_preferences jsonb not null default jsonb_build_object(
        'default_asset', 'BTC/USD',
        'default_asset_class', 'Crypto',
        'default_timeframe', '1h',
        'analysis_depth', 'Standard',
        'technical_analysis_enabled', true,
        'market_structure_enabled', true,
        'multi_timeframe_enabled', true,
        'fundamental_analysis_enabled', true,
        'news_analysis_enabled', true,
        'ai_interpretation_enabled', true
    ),
    signal_preferences jsonb not null default jsonb_build_object(
        'minimum_confidence', 0.82,
        'preferred_signal_types', jsonb_build_array('BUY', 'SELL', 'NEUTRAL'),
        'minimum_risk_reward', 1.5,
        'require_multi_timeframe_confirmation', false,
        'require_market_structure_confirmation', false
    ),
    alert_preferences jsonb not null default jsonb_build_object(
        'browser_notifications_enabled', false,
        'email_alerts_enabled', false,
        'high_confidence_signal_alerts', true,
        'price_alerts', false,
        'regime_change_alerts', false,
        'news_event_alerts', false,
        'report_completion_alerts', true,
        'frequency', 'Immediate'
    ),
    market_data_preferences jsonb not null default jsonb_build_object(
        'maximum_data_age_seconds', 300,
        'reject_stale_data', true,
        'require_completed_candles', true,
        'allow_cached_data_fallback', true
    ),
    display_preferences jsonb not null default jsonb_build_object(
        'theme', 'system',
        'density', 'comfortable',
        'sidebar_collapsed', false,
        'default_landing_page', '/dashboard',
        'currency', 'USD',
        'timezone', 'Africa/Lagos',
        'market_timestamps', 'local',
        'date_format', 'DD/MM/YYYY',
        'time_format', '24-hour',
        'reduce_animations', false
    ),
    ai_preferences jsonb not null default jsonb_build_object(
        'enabled', true,
        'analysis_style', 'Analytical',
        'interpretation_risk', 'Balanced',
        'require_evidence', true,
        'show_confidence_scores', true,
        'show_supporting_indicators', true,
        'show_conflicting_evidence', true,
        'output_sections', jsonb_build_object(
            'executive_summary', true,
            'technical_outlook', true,
            'fundamental_outlook', true,
            'news_impact', true,
            'market_regime', true,
            'bull_scenario', true,
            'base_scenario', true,
            'bear_scenario', true,
            'key_risks', true,
            'catalysts', true,
            'invalidations', true
        )
    ),
    privacy_preferences jsonb not null default jsonb_build_object(
        'research_history_retention_days', 365,
        'save_generated_reports', true,
        'save_ai_research', true,
        'save_search_history', true,
        'analytics_telemetry_enabled', true
    ),
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists user_preferences_user_id_idx
    on public.user_preferences using btree (user_id);

alter table public.user_preferences enable row level security;

revoke all on table public.user_preferences from anon, authenticated;
grant select, insert, update on table public.user_preferences to authenticated;

drop policy if exists "user_preferences_select_own" on public.user_preferences;
drop policy if exists "user_preferences_insert_own" on public.user_preferences;
drop policy if exists "user_preferences_update_own" on public.user_preferences;

create policy "user_preferences_select_own" on public.user_preferences
    for select to authenticated
    using ((select auth.uid()) = user_id);

create policy "user_preferences_insert_own" on public.user_preferences
    for insert to authenticated
    with check ((select auth.uid()) = user_id);

create policy "user_preferences_update_own" on public.user_preferences
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create or replace function public.set_user_preferences_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists user_preferences_set_updated_at on public.user_preferences;
create trigger user_preferences_set_updated_at
before update on public.user_preferences
for each row execute function public.set_user_preferences_updated_at();

-- Allows an authenticated user to permanently delete their own account.
-- Cascades remove user-owned application data such as watchlists, research
-- history, alerts and preferences through their auth.users foreign keys.
create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    delete from auth.users where id = auth.uid();
end;
$$;

revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;
