-- Explicit, version-controlled entitlement matrix.
-- This migration preserves plan-specific boundaries instead of promoting every
-- feature to Pro. Premium / Professional retains the broader platform,
-- collaboration, multi-step Copilot and live-execution entitlements.
-- Live-trade entitlement is only an authorization prerequisite; this migration
-- does not enable execution, create orders, or bypass separate approval and
-- runtime safety controls.

insert into public.billing_features (id, name, description, category)
values (
  'live_trade_execution',
  'Live trade execution',
  'Human-approved live order submission behind separate execution authorization and risk controls.',
  'PLATFORM'
)
on conflict (id) do update
set name = excluded.name,
    description = excluded.description,
    category = excluded.category;

insert into public.billing_plan_features (plan_id, feature_id, enabled)
values
  ('free', 'core_research', true),
  ('free', 'watchlists', true),
  ('free', 'basic_portfolio', true),
  ('free', 'signal_intelligence', true),
  ('free', 'ai_research', true),
  ('free', 'advanced_portfolio_analytics', false),
  ('free', 'backtesting', false),
  ('free', 'strategy_builder', false),
  ('free', 'scanner', false),
  ('free', 'webhooks', false),
  ('free', 'scheduled_workflows', false),
  ('free', 'api', false),
  ('free', 'mcp', false),
  ('free', 'exports', false),
  ('free', 'team_workspaces', false),
  ('free', 'signal_intelligence_analytics', false),
  ('free', 'advanced_research', false),
  ('free', 'enhanced_signal', false),
  ('free', 'copilot_deep_research', false),
  ('free', 'copilot_multi_step', false),
  ('free', 'phase10_intelligence', false),
  ('free', 'phase10_intelligence', false),
  ('free', 'live_trade_execution', false),
  ('pro', 'core_research', true),
  ('pro', 'watchlists', true),
  ('pro', 'basic_portfolio', true),
  ('pro', 'signal_intelligence', true),
  ('pro', 'ai_research', true),
  ('pro', 'advanced_portfolio_analytics', true),
  ('pro', 'backtesting', true),
  ('pro', 'strategy_builder', true),
  ('pro', 'scanner', true),
  ('pro', 'webhooks', false),
  ('pro', 'scheduled_workflows', true),
  ('pro', 'api', false),
  ('pro', 'mcp', false),
  ('pro', 'exports', true),
  ('pro', 'team_workspaces', false),
  ('pro', 'signal_intelligence_analytics', true),
  ('pro', 'advanced_research', true),
  ('pro', 'enhanced_signal', true),
  ('pro', 'copilot_deep_research', true),
  ('pro', 'copilot_multi_step', false),
  ('pro', 'phase10_intelligence', true),
  ('pro', 'phase10_intelligence', true),
  ('pro', 'live_trade_execution', false),
  ('premium', 'core_research', true),
  ('premium', 'watchlists', true),
  ('premium', 'basic_portfolio', true),
  ('premium', 'signal_intelligence', true),
  ('premium', 'ai_research', true),
  ('premium', 'advanced_portfolio_analytics', true),
  ('premium', 'backtesting', true),
  ('premium', 'strategy_builder', true),
  ('premium', 'scanner', true),
  ('premium', 'webhooks', true),
  ('premium', 'scheduled_workflows', true),
  ('premium', 'api', true),
  ('premium', 'mcp', true),
  ('premium', 'exports', true),
  ('premium', 'team_workspaces', true),
  ('premium', 'signal_intelligence_analytics', true),
  ('premium', 'advanced_research', true),
  ('premium', 'enhanced_signal', true),
  ('premium', 'copilot_deep_research', true),
  ('premium', 'copilot_multi_step', true),
  ('premium', 'phase10_intelligence', true),
  ('premium', 'phase10_intelligence', true),
  ('premium', 'live_trade_execution', true)
on conflict (plan_id, feature_id)
do update set enabled = excluded.enabled;
