from pathlib import Path
import re


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20261121190000_explicit_plan_entitlement_matrix.sql"
)

EXPECTED_FEATURES = {
    "core_research", "watchlists", "basic_portfolio", "signal_intelligence",
    "ai_research", "advanced_portfolio_analytics", "backtesting",
    "strategy_builder", "scanner", "webhooks", "scheduled_workflows",
    "api", "mcp", "exports", "team_workspaces",
    "signal_intelligence_analytics", "advanced_research", "enhanced_signal",
    "copilot_deep_research", "copilot_multi_step", "phase10_intelligence",
    "live_trade_execution",
}

FREE_ENABLED = {
    "core_research", "watchlists", "basic_portfolio", "signal_intelligence",
    "ai_research",
}

PRO_ENABLED = {
    "core_research", "watchlists", "basic_portfolio", "signal_intelligence",
    "ai_research", "advanced_portfolio_analytics", "backtesting",
    "strategy_builder", "scanner", "scheduled_workflows", "exports",
    "signal_intelligence_analytics", "advanced_research", "enhanced_signal",
    "copilot_deep_research", "phase10_intelligence",
}


def test_migration_defines_complete_explicit_feature_matrix():
    sql = MIGRATION.read_text(encoding="utf-8")
    rows = re.findall(
        r"\('(free|pro|premium)',\s*'([a-z0-9_]+)',\s*(true|false)\)",
        sql,
        flags=re.IGNORECASE,
    )
    assert len(rows) == len(EXPECTED_FEATURES) * 3

    matrix = {(plan, feature): enabled.lower() == "true" for plan, feature, enabled in rows}
    assert len(matrix) == len(rows)
    assert {feature for _, feature in matrix} == EXPECTED_FEATURES

    assert {feature for feature in EXPECTED_FEATURES if matrix[("free", feature)]} == FREE_ENABLED
    assert {feature for feature in EXPECTED_FEATURES if matrix[("pro", feature)]} == PRO_ENABLED
    assert all(matrix[("premium", feature)] for feature in EXPECTED_FEATURES)

    # Explicitly protect Premium-only boundaries from a blanket Pro enable.
    for feature in ("webhooks", "api", "mcp", "team_workspaces", "copilot_multi_step", "live_trade_execution"):
        assert matrix[("pro", feature)] is False
        assert matrix[("premium", feature)] is True


def test_migration_does_not_modify_plan_usage_limits():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "billing_plan_limits" not in sql
    assert "limit_value" not in sql
