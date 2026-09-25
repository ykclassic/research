alter table public.quant_experiments
  add column if not exists strategy_id text,
  add column if not exists dataset_fingerprint text,
  add column if not exists spec_hash text,
  add column if not exists trade_count integer not null default 0;

update public.quant_experiments
set strategy_id = coalesce(strategy_id, 'unknown'),
    dataset_fingerprint = coalesce(dataset_fingerprint, dataset_version),
    spec_hash = coalesce(spec_hash, md5(id::text) || md5(created_at::text))
where strategy_id is null or dataset_fingerprint is null or spec_hash is null;

alter table public.quant_experiments
  alter column strategy_id set not null,
  alter column dataset_fingerprint set not null,
  alter column spec_hash set not null;

create unique index if not exists quant_experiments_user_spec_hash_idx
  on public.quant_experiments(user_id, spec_hash);

alter table public.quant_experiments
  drop constraint if exists quant_experiments_split_order;

alter table public.quant_experiments
  add constraint quant_experiments_split_order check (
    train_start < train_end and train_end < validation_start and
    validation_start < validation_end and validation_end < test_start and
    test_start < test_end
  );

alter table public.paper_trades
  add column if not exists experiment_id uuid references public.quant_experiments(id) on delete set null;

create index if not exists paper_trades_experiment_idx
  on public.paper_trades(experiment_id);

revoke update, delete on public.quant_experiments from authenticated;
grant select, insert on public.quant_experiments to authenticated;

drop policy if exists quant_experiments_own on public.quant_experiments;
create policy quant_experiments_select_own on public.quant_experiments
  for select to authenticated
  using ((select auth.uid()) = user_id);

create policy quant_experiments_insert_own on public.quant_experiments
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
