-- Phase 2: persistent, user-owned watchlists.
-- Apply this migration in the Supabase project before enabling the watchlist UI.

create table if not exists public.watchlists (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    name text not null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint watchlists_name_length check (char_length(trim(name)) between 1 and 80),
    constraint watchlists_user_name_unique unique (user_id, name)
);

create table if not exists public.watchlist_items (
    id uuid primary key default gen_random_uuid(),
    watchlist_id uuid not null references public.watchlists(id) on delete cascade,
    symbol text not null,
    created_at timestamptz not null default timezone('utc', now()),
    constraint watchlist_items_symbol_length check (char_length(trim(symbol)) between 1 and 32),
    constraint watchlist_items_unique_symbol unique (watchlist_id, symbol)
);

create index if not exists watchlists_user_id_idx
    on public.watchlists using btree (user_id);

create index if not exists watchlist_items_watchlist_id_idx
    on public.watchlist_items using btree (watchlist_id);

alter table public.watchlists enable row level security;
alter table public.watchlist_items enable row level security;

revoke all on table public.watchlists from anon, authenticated;
revoke all on table public.watchlist_items from anon, authenticated;

grant select, insert, update, delete on table public.watchlists to authenticated;
grant select, insert, update, delete on table public.watchlist_items to authenticated;

drop policy if exists "watchlists_select_own" on public.watchlists;
drop policy if exists "watchlists_insert_own" on public.watchlists;
drop policy if exists "watchlists_update_own" on public.watchlists;
drop policy if exists "watchlists_delete_own" on public.watchlists;

drop policy if exists "watchlist_items_select_own" on public.watchlist_items;
drop policy if exists "watchlist_items_insert_own" on public.watchlist_items;
drop policy if exists "watchlist_items_update_own" on public.watchlist_items;
drop policy if exists "watchlist_items_delete_own" on public.watchlist_items;

create policy "watchlists_select_own"
on public.watchlists
for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "watchlists_insert_own"
on public.watchlists
for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "watchlists_update_own"
on public.watchlists
for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "watchlists_delete_own"
on public.watchlists
for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "watchlist_items_select_own"
on public.watchlist_items
for select
to authenticated
using (
    exists (
        select 1
        from public.watchlists w
        where w.id = watchlist_items.watchlist_id
          and (select auth.uid()) = w.user_id
    )
);

create policy "watchlist_items_insert_own"
on public.watchlist_items
for insert
to authenticated
with check (
    exists (
        select 1
        from public.watchlists w
        where w.id = watchlist_items.watchlist_id
          and (select auth.uid()) = w.user_id
    )
);

create policy "watchlist_items_update_own"
on public.watchlist_items
for update
to authenticated
using (
    exists (
        select 1
        from public.watchlists w
        where w.id = watchlist_items.watchlist_id
          and (select auth.uid()) = w.user_id
    )
)
with check (
    exists (
        select 1
        from public.watchlists w
        where w.id = watchlist_items.watchlist_id
          and (select auth.uid()) = w.user_id
    )
);

create policy "watchlist_items_delete_own"
on public.watchlist_items
for delete
to authenticated
using (
    exists (
        select 1
        from public.watchlists w
        where w.id = watchlist_items.watchlist_id
          and (select auth.uid()) = w.user_id
    )
);

create or replace function public.set_watchlist_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists watchlists_set_updated_at on public.watchlists;
create trigger watchlists_set_updated_at
before update on public.watchlists
for each row execute function public.set_watchlist_updated_at();
