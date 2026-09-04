create table if not exists public.mtf_candle_cache (
    user_id uuid not null references auth.users(id) on delete cascade,
    symbol text not null,
    timeframe text not null,
    range_key text not null default 'recent',
    dataset jsonb not null,
    updated_at timestamptz not null default now(),
    primary key (user_id, symbol, timeframe, range_key)
);

alter table public.mtf_candle_cache enable row level security;

create policy "Users can read their MTF candle cache"
    on public.mtf_candle_cache for select
    using (auth.uid() = user_id);

create policy "Users can insert their MTF candle cache"
    on public.mtf_candle_cache for insert
    with check (auth.uid() = user_id);

create policy "Users can update their MTF candle cache"
    on public.mtf_candle_cache for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy "Users can delete their MTF candle cache"
    on public.mtf_candle_cache for delete
    using (auth.uid() = user_id);

create index if not exists mtf_candle_cache_lookup_idx
    on public.mtf_candle_cache (user_id, symbol, timeframe, updated_at desc);
