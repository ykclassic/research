-- Phase 9: scheduled machine-readable exports.

create table if not exists public.research_export_schedules (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  resource_type text not null check (resource_type in ('RUNS','SNAPSHOTS','OUTCOMES')),
  format text not null check (format in ('JSON','CSV')),
  interval_minutes integer not null check (interval_minutes between 15 and 43200),
  next_run_at timestamptz not null,
  last_run_at timestamptz,
  enabled boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);
create index if not exists research_export_schedules_due_idx on public.research_export_schedules(enabled,next_run_at);
create index if not exists research_export_schedules_user_idx on public.research_export_schedules(user_id,created_at desc);

alter table public.research_export_schedules enable row level security;
revoke all on public.research_export_schedules from anon;
grant select,insert,update,delete on public.research_export_schedules to authenticated;
grant select,insert,update,delete on public.research_export_schedules to service_role;
create policy research_export_schedules_own on public.research_export_schedules for all to authenticated
using ((select auth.uid())=user_id) with check ((select auth.uid())=user_id);

drop trigger if exists research_export_schedules_updated_at on public.research_export_schedules;
create trigger research_export_schedules_updated_at before update on public.research_export_schedules for each row execute function public.set_phase9_updated_at();
