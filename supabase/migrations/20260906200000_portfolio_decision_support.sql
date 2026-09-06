create table if not exists public.portfolio_positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  side text not null check (side in ('LONG','SHORT')),
  quantity numeric(30,10) not null check (quantity > 0),
  average_entry_price numeric(30,10) not null check (average_entry_price > 0),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists portfolio_positions_user_idx on public.portfolio_positions(user_id);
create index if not exists portfolio_positions_symbol_idx on public.portfolio_positions(user_id, symbol);

alter table public.portfolio_positions enable row level security;
grant select, insert, update, delete on public.portfolio_positions to authenticated;

drop policy if exists portfolio_positions_select_own on public.portfolio_positions;
create policy portfolio_positions_select_own on public.portfolio_positions for select to authenticated using (user_id = auth.uid());
drop policy if exists portfolio_positions_insert_own on public.portfolio_positions;
create policy portfolio_positions_insert_own on public.portfolio_positions for insert to authenticated with check (user_id = auth.uid());
drop policy if exists portfolio_positions_update_own on public.portfolio_positions;
create policy portfolio_positions_update_own on public.portfolio_positions for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists portfolio_positions_delete_own on public.portfolio_positions;
create policy portfolio_positions_delete_own on public.portfolio_positions for delete to authenticated using (user_id = auth.uid());

create or replace function public.set_portfolio_positions_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;
drop trigger if exists portfolio_positions_updated_at on public.portfolio_positions;
create trigger portfolio_positions_updated_at before update on public.portfolio_positions for each row execute function public.set_portfolio_positions_updated_at();
