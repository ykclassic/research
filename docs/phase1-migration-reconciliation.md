# Phase 1 migration reconciliation — first pass

Read-only audit of repository commit `4d5eefeb6cd231a7b733db508035fa869814ad7b` against Supabase project `rprgjfvfttxydhbekuoc`. No schema or migration history was changed.

## Counts

- Repository: 33 SQL files under `supabase/migrations/`.
- Supabase migration ledger: 29 records.
- Live catalog query: workspace and signal-intelligence objects exist; the objects listed below do not.
- Count difference is not, by itself, a safe migration plan. Names/timestamps differ, duplicate Phase 4 ledger entries exist, and object presence alone does not prove matching policies or constraints.

## Repository files without exact ledger-name matches

| Migration file | Expected live effect | Observed evidence | Initial classification |
|---|---|---|---|
| `20260904090000_mtf_candle_cache.sql` | `public.mtf_candle_cache` | Table absent | NOT_APPLIED |
| `20260922010000_signal_intelligence_analytics.sql` | `signal_intelligence`, `signal_intelligence_analytics` billing feature and grants/policies | Table and feature exist | SCHEMA_PRESENT_LEDGER_MISMATCH; inspect policy/grant equivalence |
| `20260925120000_phase6_quant_lab.sql` | `quant_experiments`, `paper_portfolios`, `paper_trades` | All three tables absent | NOT_APPLIED |
| `20260925220000_quant_experiment_contract.sql` | Adds contract fields/indexes to quant tables | Base tables absent | NOT_APPLIED / dependency blocked |
| `20260925233000_phase6_strategy_builder_validation.sql` | `strategy_definitions` | Table absent | NOT_APPLIED |
| `20260926100000_phase8_research_workspaces.sql` | Workspace, asset, dashboard, link, scorecard, automation and cross-asset tables | Workspace tables and related objects present | SCHEMA_PRESENT_LEDGER_MISMATCH; inspect full schema/security equivalence |
| `20260926103000_phase8_research_entitlement.sql` | `advanced_research` feature and plan-feature rows | Feature exists | SCHEMA_PRESENT_LEDGER_MISMATCH; verify plan-feature rows |

## Ledger entries without exact repository counterparts

- `20260925021944 / phase4_research_intelligence`
- `20260925024319 / phase4_research_intelligence`
- `20260925221413 / 20260925230000_pro_premium_feature_parity`

The ledger also has `20260923141140 / phase4_research_intelligence`, while the repository has one `20260923150000_phase4_research_intelligence.sql`. Do not assume these duplicate entries are harmless or interchangeable. Classify them as UNRESOLVED until their SQL effects are compared with catalog definitions and historical commits.

## What the first pass establishes

Four repository migrations have absent expected objects; three repository migrations have evidence of their effects but no exact ledger match; three live ledger entries lack exact one-to-one repository counterparts. This explains the 33-file/29-record count without proving full schema equivalence.

## Required reconciliation before any migration action

For each file and ledger row, compare SQL content/checksum, created objects, columns, constraints, indexes, policies, grants, triggers, functions, seed/entitlement rows, dependent migrations, and historical commits. Record one of:

- MATCHED
- SCHEMA_PRESENT_LEDGER_MISMATCH
- LEDGER_PRESENT_SCHEMA_MISSING
- NOT_APPLIED
- SUPERSEDED
- UNRESOLVED

No production migration should be applied, marked applied, deleted, squashed, or repaired until this matrix has been reviewed. The live catalog must be checked for all security objects as well as table names; a present table does not prove that its RLS policies or grants match the migration source.
