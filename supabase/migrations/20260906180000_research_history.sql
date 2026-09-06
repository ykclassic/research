-- Phase 11: persistent, user-owned research history.
-- Stores auditable report snapshots, searches, and AI analyses.

create table if not exists public.research_history (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    record_type text not null check (record_type in ('REPORT', 'SEARCH', 'AI_ANALYSIS')),
    symbol text,
    query text,
    title text,
    payload jsonb not null default '{}'::jsonb,
    saved boolean not null default false,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint research_history_symbol_length check (symbol is null or char_length(trim(symbol)) between 1 and 32),
    constraint research_history_query_length check (query is null or char_length(query) <= 2000),
    constraint research_history_title_length check (title is null or char_length(title) <= 200),
    constraint research_history_payload_object check (jsonb_typeof(payload) = 'object')
);

create index if not exists research_history_user_created_idx
    on public.research_history using btree (user_id, created_at desc);
create index if not exists research_history_user_symbol_idx
    on public.research_history using btree (user_id, symbol);
create index if not exists research_history_user_type_idx
    on public.research_history using btree (user_id, record_type, created_at desc);
create index if not exists research_history_user_saved_idx
    on public.research_history using btree (user_id, saved, created_at desc);

create table if not exists public.research_notes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    history_id uuid not null references public.research_history(id) on delete cascade,
    note text not null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint research_notes_length check (char_length(trim(note)) between 1 and 5000)
);

create index if not exists research_notes_user_history_idx
    on public.research_notes using btree (user_id, history_id, created_at desc);

alter table public.research_history enable row level security;
alter table public.research_notes enable row level security;

revoke all on table public.research_history from anon, authenticated;
revoke all on table public.research_notes from anon, authenticated;
grant select, insert, update, delete on table public.research_history to authenticated;
grant select, insert, update, delete on table public.research_notes to authenticated;

drop policy if exists "research_history_select_own" on public.research_history;
drop policy if exists "research_history_insert_own" on public.research_history;
drop policy if exists "research_history_update_own" on public.research_history;
drop policy if exists "research_history_delete_own" on public.research_history;
drop policy if exists "research_notes_select_own" on public.research_notes;
drop policy if exists "research_notes_insert_own" on public.research_notes;
drop policy if exists "research_notes_update_own" on public.research_notes;
drop policy if exists "research_notes_delete_own" on public.research_notes;

create policy "research_history_select_own" on public.research_history for select to authenticated using ((select auth.uid()) = user_id);
create policy "research_history_insert_own" on public.research_history for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "research_history_update_own" on public.research_history for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "research_history_delete_own" on public.research_history for delete to authenticated using ((select auth.uid()) = user_id);

create policy "research_notes_select_own" on public.research_notes for select to authenticated using ((select auth.uid()) = user_id);
create policy "research_notes_insert_own" on public.research_notes for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "research_notes_update_own" on public.research_notes for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "research_notes_delete_own" on public.research_notes for delete to authenticated using ((select auth.uid()) = user_id);

create or replace function public.set_research_history_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists research_history_set_updated_at on public.research_history;
create trigger research_history_set_updated_at before update on public.research_history for each row execute function public.set_research_history_updated_at();

drop trigger if exists research_notes_set_updated_at on public.research_notes;
create trigger research_notes_set_updated_at before update on public.research_notes for each row execute function public.set_research_history_updated_at();
