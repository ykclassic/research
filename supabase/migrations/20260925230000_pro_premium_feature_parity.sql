-- Phase 6 / monetization: Pro and Premium / Professional expose the same feature set.
-- Usage limits remain plan-specific; feature availability is intentionally identical.
insert into public.billing_plan_features(plan_id, feature_id, enabled)
select 'pro', id, true
from public.billing_features
on conflict (plan_id, feature_id) do update set enabled = excluded.enabled;
