alter table public.portfolio_positions
  add column if not exists asset_class text not null default 'OTHER',
  add column if not exists sector text not null default 'OTHER',
  add column if not exists category text not null default 'OTHER';

alter table public.portfolio_positions
  drop constraint if exists portfolio_positions_asset_class_check;
alter table public.portfolio_positions
  add constraint portfolio_positions_asset_class_check
  check (asset_class in ('CRYPTO','FOREX','STOCK','ETF','COMMODITY','INDEX','OTHER'));

create index if not exists portfolio_positions_classification_idx
  on public.portfolio_positions(user_id, asset_class, sector, category);
