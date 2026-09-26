-- Phase 10: model version governance guardrails.
-- Version identity and evaluation windows are immutable after creation. Only the
-- explicit evaluation/promotion/rollback workflow may change lifecycle fields.
create or replace function public.phase10_guard_model_version_update()
returns trigger
language plpgsql
as $$
begin
  if new.model_id <> old.model_id
     or new.user_id <> old.user_id
     or new.version <> old.version
     or new.dataset_version <> old.dataset_version
     or new.feature_version <> old.feature_version
     or new.training_period_start <> old.training_period_start
     or new.training_period_end <> old.training_period_end
     or new.validation_period_start <> old.validation_period_start
     or new.validation_period_end <> old.validation_period_end
     or new.test_period_start <> old.test_period_start
     or new.test_period_end <> old.test_period_end then
    raise exception 'Phase 10 model version identity and evaluation windows are immutable.';
  end if;
  return new;
end;
$$;

drop trigger if exists phase10_model_version_guard on public.research_model_versions;
create trigger phase10_model_version_guard
before update on public.research_model_versions
for each row execute function public.phase10_guard_model_version_update();

create index if not exists research_model_events_version_time
on public.research_model_events(model_version_id,created_at desc);
create index if not exists product_events_event_feature_time
on public.product_events(event_name,feature,occurred_at desc);
