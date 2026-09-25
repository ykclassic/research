create table if not exists public.quant_experiments (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 strategy_id text not null,
 strategy_version text not null,
 dataset_version text not null,
 dataset_fingerprint text not null,
 feature_version text not null,
 spec_hash text not null,
 parameters jsonb not null default '{}'::jsonb,
 costs jsonb not null default '{}'::jsonb,
 execution jsonb not null default '{}'::jsonb,
 train_start timestamptz not null,
 train_end timestamptz not null,
 validation_start timestamptz not null,
 validation_end timestamptz not null,
 test_start timestamptz not null,
 test_end timestamptz not null,
 engine_version text not null,
 trade_count integer not null default 0,
 metrics jsonb not null default '{}'::jsonb,
 created_at timestamptz not null default timezone('utc',now()),
 constraint quant_experiments_split_order check (
   train_start < train_end and train_end < validation_start and
   validation_start < validation_end and validation_end < test_start and test_start < test_end
 ),
 constraint quant_experiments_spec_hash_len check (length(spec_hash) = 64)
);
create unique index if not exists quant_experiments_user_spec_hash_idx on public.quant_experiments(user_id,spec_hash);
create index if not exists quant_experiments_user_time_idx on public.quant_experiments(user_id,created_at desc);

create table if not exists public.paper_portfolios (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 name text not null,
 base_currency text not null default 'USD',
 starting_equity numeric not null,
 equity numeric not null,
 drawdown numeric not null default 0,
 created_at timestamptz not null default timezone('utc',now())
);
create table if not exists public.paper_trades (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 portfolio_id uuid not null references public.paper_portfolios(id) on delete cascade,
 experiment_id uuid references public.quant_experiments(id) on delete set null,
 symbol text not null,
 side text not null check(side in ('LONG','SHORT')),
 quantity numeric not null,
 entry_price numeric not null,
 entry_time timestamptz not null,
 exit_price numeric,
 exit_time timestamptz,
 pnl numeric,
 strategy_id text,
 signal_id text,
 status text not null default 'OPEN' check(status in ('OPEN','CLOSED'))
);
create index if not exists paper_trades_user_portfolio_time_idx on public.paper_trades(user_id,portfolio_id,entry_time desc);
create index if not exists paper_trades_experiment_idx on public.paper_trades(experiment_id);

alter table public.quant_experiments enable row level security;
alter table public.paper_portfolios enable row level security;
alter table public.paper_trades enable row level security;

revoke all on table public.quant_experiments from anon;
revoke update,delete on table public.quant_experiments from authenticated;
grant select,insert on public.quant_experiments to authenticated;

revoke all on table public.paper_portfolios,public.paper_trades from anon;
grant select,insert,update,delete on public.paper_portfolios to authenticated;
grant select,insert,update on public.paper_trades to authenticated;

drop policy if exists quant_experiments_own on public.quant_experiments;
create policy quant_experiments_select_own on public.quant_experiments for select to authenticated using ((select auth.uid())=user_id);
create policy quant_experiments_insert_own on public.quant_experiments for insert to authenticated with check ((select auth.uid())=user_id);

drop policy if exists paper_portfolios_own on public.paper_portfolios;
create policy paper_portfolios_own on public.paper_portfolios for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);

drop policy if exists paper_trades_own on public.paper_trades;
create policy paper_trades_own on public.paper_trades for all to authenticated using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);
