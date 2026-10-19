# Phase 1 migration reconciliation — row-by-row matrix

**Scope:** read-only comparison of the 33 migration files in repository `main` at `4d5eefeb6cd231a7b733db508035fa869814ad7b`, the 29-row Supabase migration ledger, and live catalog/RLS/grant evidence queried from project `rprgjfvfttxydhbekuoc`. No production DDL or ledger edits were made.

## Reconciliation matrix

| # | Repository migration | Ledger evidence | Live catalog evidence | Classification |
|---:|---|---|---|---|
| 1 | `20260824233618_watchlists_phase_2.sql` | `watchlists_phase_2` | `watchlists`, `watchlist_items` present; RLS enabled | MATCHED by name/effect; timestamp alias |
| 2 | `20260904090000_mtf_candle_cache.sql` | No matching row | `mtf_candle_cache` absent | NOT_APPLIED; verify no code path requires it before scheduling a later migration |
| 3 | `20260906180000_research_history.sql` | `20260906180000_research_history` at ledger version `20260906192011` | `research_history`, `research_notes` present | MATCHED by name/effect; ledger version differs from filename timestamp |
| 4 | `20260906190000_alerts_monitoring.sql` | `20260906190000_alerts_monitoring` at `20260906191758` | `alert_rules`, `alert_events` present; RLS enabled | MATCHED by name/effect; timestamp alias |
| 5 | `20260906200000_portfolio_decision_support.sql` | `portfolio_decision_support` at `20260906212023` | `portfolio_positions` present; RLS enabled; 4 policies | MATCHED by name/effect; timestamp alias |
| 6 | `20260913200000_settings_foundation.sql` | `settings_foundation` at `20260913220130` | `user_preferences` present | MATCHED by name/effect; timestamp alias |
| 7 | `20260913201000_settings_security_hardening.sql` | `settings_security_hardening` at `20260913220211` | `delete_my_account()` has `search_path=public`; execution denied to anon and allowed to authenticated; `set_user_preferences_updated_at()` has `search_path=public` | MATCHED by name and inspected function config/grants |
| 8 | `20260919200000_signal_outcome_target_tag_audit.sql` | `signal_outcome_target_tag_audit` at `20260919225814` | `signal_outcome_audit` present; mutation-rejection trigger previously observed | MATCHED by name/effect; timestamp alias |
| 9 | `20260921120000_monetization_entitlements.sql` | `20260921120000_monetization_entitlements` at `20260921222914` | Billing plans/features/limits/subscriptions/events and usage tables present | MATCHED by name/effect; **grant review remains open** |
| 10 | `20260922000000_usage_threshold_notifications.sql` | `billing_usage_notifications_table` at `20260922092753` | `billing_usage_notifications` present; `consume_usage` exists | MATCHED by effect/alias; timestamp/name differs |
| 11 | `20260922010000_signal_intelligence_analytics.sql` | No exact matching row | Feature row present; live numeric precisions on `signal_intelligence` (e.g. `entry_price numeric(30,12)`, `confidence numeric(12,10)`) match this file | SCHEMA_PRESENT_LEDGER_MISMATCH; this file’s table definition appears to have taken effect outside a matching ledger row |
| 12 | `20260922044929_signal_intelligence.sql` | `signal_intelligence` at `20260922044929` | Table present, RLS enabled, 2 owner-scoped policies; authenticated SELECT/INSERT grants observed | MATCHED for canonical policy/index/grant effects; `CREATE TABLE IF NOT EXISTS` did not replace row 11 numeric precision choices |
| 13 | `20260922090000_phase3_scanner.sql` | `phase3_scanner_market_scanner_alert_engine` at `20260922052245` | Scanner presets/runs/opportunities/schedules/alert events present | MATCHED by effect/alias; timestamp precedes filename |
| 14 | `20260923000000_phase3_scanner_completion.sql` | `phase3_scanner_completion` at `20260923192326` | `scanner_alert_deliveries` present; `scanner_opportunities` altered by source migration | MATCHED by name/effect; timestamp alias; compare delivery columns and policy expressions |
| 15 | `20260923150000_phase4_research_intelligence.sql` | Three ledger rows named `phase4_research_intelligence` at `20260923141140`, `20260925021944`, `20260925024319` | Research snapshots/provenance/watchpoints/watchpoint events/catalyst events present | SCHEMA_PRESENT_LEDGER_MISMATCH; one file vs three ledger entries; provenance of two extra entries unresolved |
| 16 | `20260923193000_phase3_completion_gates.sql` | `phase3_completion_gates` at `20260923192326` | No table creation expected; migration is a completion-gate script | MATCHED by name/effect; confirm exact script history/checksum |
| 17 | `20260923194500_phase4_completion_gates.sql` | `phase4_completion_gates` at `20260923193016` | `research_catalyst_events` and related alterations present | MATCHED by name/effect; timestamp alias |
| 18 | `20260923200000_phase5_grounded_copilot.sql` | `phase5_grounded_copilot` at `20260923193748` | `research_runs`, `research_schedules` present | MATCHED by name/effect; timestamp alias |
| 19 | `20260925120000_phase6_quant_lab.sql` | No matching row | `quant_experiments`, `paper_portfolios`, `paper_trades` absent | NOT_APPLIED |
| 20 | `20260925220000_quant_experiment_contract.sql` | No matching row | Base quant tables absent, so its target columns/indexes cannot exist | DEPENDENCY_BLOCKED / NOT_APPLIED |
| 21 | `20260925233000_phase6_strategy_builder_validation.sql` | No matching row | `strategy_definitions` absent | NOT_APPLIED |
| 22 | `20260925240000_phase7_portfolio_intelligence.sql` | `phase7_portfolio_intelligence` at `20260925230252` | `portfolio_positions` present | MATCHED by effect/alias; timestamp differs |
| 23 | `20260926003000_phase10_optimization_intelligence.sql` | `phase10_optimization_intelligence` at `20260926075534` | Chart events, fundamentals, models/versions/events, cache entries and product events present | MATCHED by effect/alias; cache table has RLS but no policies and is service-role-only |
| 24 | `20260926010000_phase10_model_governance_guardrails.sql` | `phase10_model_governance_guardrails` at `20260926081941` | `phase10_guard_model_version_update()` exists and enabled trigger `phase10_model_version_guard` is attached to `research_model_versions` | MATCHED by name and trigger attachment; source behavior was inspected |
| 25 | `20260926100000_phase8_research_workspaces.sql` | No exact matching row | All seven workspace-related tables present; RLS enabled; expected owner/shared policy families present | SCHEMA_PRESENT_LEDGER_MISMATCH; compare all columns/constraints/policies to source SQL |
| 26 | `20260926103000_phase8_research_entitlement.sql` | No exact matching row | `advanced_research` feature exists | SCHEMA_PRESENT_LEDGER_MISMATCH; verify every plan-feature row and its provenance |
| 27 | `20260926120000_phase9_infrastructure.sql` | `phase9_infrastructure` at `20260926001951` | API keys, webhooks, organizations, members, shares, audit log and exports present | MATCHED by name/effect; timestamp alias |
| 28 | `20260926123000_phase9_shared_resource_rls.sql` | `phase9_shared_resource_rls` at `20260926002146` | Workspace/shared resource policy families present | MATCHED by name/effect; compare policy expressions and grants |
| 29 | `20260926124500_phase9_scheduled_exports.sql` | `phase9_scheduled_exports` at `20260926002238` | `research_export_schedules` present | MATCHED by name/effect; timestamp alias |
| 30 | `20261002090000_enhanced_signal_entitlement.sql` | `enhanced_signal_entitlement` at `20261002122943` | `enhanced_signal` feature exists | MATCHED by name/effect; verify plan-feature rows |
| 31 | `20261006090000_billing_paid_plan_lifecycle.sql` | `billing_paid_plan_lifecycle` at `20261006212641` | `consume_usage` exists but was subsequently replaced by row 32 | SUPERSEDED by row 32; preserve this history rather than comparing only the final function body |
| 32 | `20261007190000_fix_consume_usage_period_start_ambiguity.sql` | `fix_consume_usage_period_start_ambiguity` at `20261007200501` | Current `consume_usage` body has qualified columns, `search_path` empty, and `auth.uid() = p_user_id` guard | MATCHED; inspected live function body/config |
| 33 | `20261007211000_fix_consume_api_usage_period_start_ambiguity.sql` | `fix_consume_api_usage_period_start_ambiguity` at `20261007210815` | Live `consume_api_usage` body matches the qualified period-start implementation; empty `search_path`; execute denied to anon/authenticated and granted to service_role | MATCHED; inspected live function body/config/grants |

## Ledger rows without a one-to-one repository file

| Ledger version | Ledger name | Classification |
|---|---|---|
| `20260925021944` | `phase4_research_intelligence` | UNRESOLVED duplicate; no second repository migration |
| `20260925024319` | `phase4_research_intelligence` | UNRESOLVED duplicate; no third repository migration |
| `20260925221413` | `20260925230000_pro_premium_feature_parity` | UNRESOLVED; no exact repository file; inspect plan-feature data and historical commit |

The row at `20260923141140 / phase4_research_intelligence` is the first plausible match for the repository Phase 4 file, but its version differs from the repository timestamp. It cannot establish which later duplicate entries ran or whether they changed schema/data.

## Catalog security evidence

The live catalog confirms RLS enabled on the inspected billing, portfolio, signal, cache, and workspace tables. It also shows role grants broader than the source migration's explicit grants on several billing and workspace tables. RLS policies are a separate control from table grants; grants should be narrowed only after reviewing the policy expressions and actual application access patterns. `research_cache_entries` has RLS enabled with no policies and service-role-only grants, which is a deliberate fail-closed pattern if all access is intended to remain backend-only.

The matrix's status indicates best-supported effect mapping, not cryptographic SQL equivalence. Exact source checksums and full function/trigger/policy expressions are still needed for the rows explicitly flagged above. No migration was applied, marked applied, deleted, or repaired in production.

## Execution migration testing boundary

The new execution persistence migration lives only in the repository branch. A disposable PostgreSQL 16 GitHub Actions service is configured to create minimal `auth.users` and test roles, apply the migration, and test transactional RPCs, idempotency, rejected-intent isolation, single-use claim, browser-role denial, and append-only triggers. It is not connected to production Supabase.
