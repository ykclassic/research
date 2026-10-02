-- Enhanced Signal entitlement.
-- Pro and Premium / Professional receive Enhanced Signal as their production
-- signal-generation surface. The legacy signal engine remains available to
-- lower tiers during the validation period and is not silently promoted.

insert into public.billing_features(id,name,description,category)
values (
  'enhanced_signal',
  'Enhanced Signal',
  'Deterministic price-action and SMC signal generation with HTF alignment, liquidity sweeps, POI validation, structural invalidation, path-to-target checks and outcome telemetry.',
  'INTELLIGENCE'
)
on conflict (id) do update set
  name=excluded.name,
  description=excluded.description,
  category=excluded.category;

insert into public.billing_plan_features(plan_id,feature_id,enabled)
values
  ('free','enhanced_signal',false),
  ('pro','enhanced_signal',true),
  ('premium','enhanced_signal',true)
on conflict (plan_id,feature_id) do update set enabled=excluded.enabled;
