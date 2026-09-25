create table if not exists public.strategy_definitions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  version text not null,
  definition jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  unique(user_id, name, version)
);

create index if not exists strategy_definitions_user_created_idx
  on public.strategy_definitions(user_id, created_at desc);

alter table public.strategy_definitions enable row level security;

drop policy if exists strategy_definitions_select on public.strategy_definitions;
create policy strategy_definitions_select on public.strategy_definitions
  for select using (auth.uid() = user_id);

drop policy if exists strategy_definitions_insert on public.strategy_definitions;
create policy strategy_definitions_insert on public.strategy_definitions
  for insert with check (auth.uid() = user_id);

revoke update, delete on public.strategy_definitions from authenticated;
grant select, insert on public.strategy_definitions to authenticated;