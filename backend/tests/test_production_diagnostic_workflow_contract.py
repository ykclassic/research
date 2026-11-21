from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "production-market-data-verification.yml"
)


def test_production_verification_runs_on_main_pushes():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "on:\n  push:\n    branches:\n      - main" in source
    assert 'claims.get("event_name") in {"push", "schedule", "workflow_dispatch"}' in source


def test_production_workflow_uses_current_database_diagnostic_contract():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'diagnostic.get("status") != "passed"' in source
    assert 'diagnostic.get("reason_code") is not None' in source
    assert 'diagnostic.get("probe_method") != "postgrest_service_role_read_only_select_billing_plans_limit_1"' in source
    assert 'diagnostic.get("deployment_sha")' in source

    # Prevent regression to the superseded diagnostic response schema.
    assert 'diagnostic.get("configured")' not in source
    assert 'diagnostic.get("database_probe")' not in source
    assert 'diagnostic.get("probe_kind")' not in source
    assert 'diagnostic.get("deployment_commit")' not in source
