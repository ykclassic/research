from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.api import diagnostics as diagnostics_api
from app.api.auth import require_github_actions
from app.config import settings
from app.main import app
from app.services.supabase_data import DataUnavailableError


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    app.dependency_overrides[require_github_actions] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_database_diagnostic_reports_only_sanitized_target_and_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://rprgjfvfttxydhbekuoc.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "test-commit-sha")
    calls = []

    def probe(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return object()

    monkeypatch.setattr(diagnostics_api, "service_request", probe)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "project_ref": "rprgjfvfttxydhbekuoc",
        "database_probe": "ok",
        "probe_kind": "read_only_postgrest_billing_plans_limit_1",
        "deployment_commit": "test-commit-sha",
    }
    assert calls == [("GET", "billing_plans", {"params": {"select": "id", "limit": "1"}})]
    assert "server-only-test-key" not in response.text
    assert "supabase.co" not in response.text


def test_database_diagnostic_sanitizes_probe_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://rprgjfvfttxydhbekuoc.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")

    def fail(*args, **kwargs):
        raise DataUnavailableError("secret URL and credentials must not be returned")

    monkeypatch.setattr(diagnostics_api, "service_request", fail)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["database_probe"] == "failed"
    assert response.json()["project_ref"] == "rprgjfvfttxydhbekuoc"
    assert "secret URL" not in response.text
    assert "server-only-test-key" not in response.text


def test_database_diagnostic_does_not_claim_unrecognized_target(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.invalid")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")
    monkeypatch.setattr(
        diagnostics_api,
        "service_request",
        lambda *args, **kwargs: pytest.fail("probe must not run for an unrecognized target"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["project_ref"] is None
    assert response.json()["database_probe"] == "failed"



def test_database_diagnostic_never_sends_service_key_to_wrong_supabase_project(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://aaaaaaaaaaaaaaaaaaaa.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")
    monkeypatch.setattr(
        diagnostics_api,
        "service_request",
        lambda *args, **kwargs: pytest.fail("must not probe a project other than the expected production target"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["project_ref"] == "aaaaaaaaaaaaaaaaaaaa"
    assert response.json()["database_probe"] == "failed"
