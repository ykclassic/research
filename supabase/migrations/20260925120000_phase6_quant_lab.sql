create table if not exists public.quant_experiments (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 dataset_version text not null, strategy_version text not null, feature_version text not null,
 parameters jsonb not null default '{}'::jsonb, costs jsonb not null default '{}'::jsonb, execution jsonb not null default '{}'::jsonb,
 train_start timestamptz not null, train_end timestamptz not null, validation_start timestamptz not null, validation_end timestamptz not null,
 test_start timestamptz not null, test_end timestamptz not null, engine_version text not null, metrics jsonb not null default '{}'::jsonb, created_at timestamptz not null default timezone('utc',now())
);
create index if not exists quant_experiments_user_time_idx on public.quant_experiments(user_id,created_at desc);
create table if not exists public.paper_portfolios (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 name text not null, base_currency text not null default 'USD', starting_equity numeric not null, equity numeric not null, drawdown numeric not null default 0, created_at timestamptz not null default timezone('utc',now())
);
create table if not exists public.paper_trades (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id) on delete cascade,
 portfolio_id uuid not null references public.paper_portfolios(id) on delete cascade, symbol text not null, side text not null check(side in ('LONG','SHORT')),
 quantity numeric not null, entry_price numeric not null, entry_time timestamptz not null, exit_price numeric, exit_time timestamptz, pnl numeric,
 strategy_id text, signal_id text, status text not null default 'OPEN' check(status in ('OPEN','CLOSED'))
);
create index if not exists paper_trades_user_portfolio_time_idx on public.paper_trades(user_id,portfolio_id,entry_time desc);
alter table public.quant_experiments enable row level security;
alter table public.paper_portfolios enable row level security;
alter table public.paper_trades enable row level security;
revoke all on table public.quant_experiments,public.paper_portfolios,public.paper_trades from anon;
grant select,insert on public.quant_experiments to authenticated;
grant select,insert,update,delete on public.paper_portfolios to authenticated;
grant select,insert,update on public.paper_trades to authenticated;
create policy quant_experiments_own on public.quant_experiments for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy paper_portfolios_own on public.paper_portfolios for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
create policy paper_trades_own on public.paper_trades for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
