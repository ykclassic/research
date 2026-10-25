from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.api.auth import require_github_actions
from app.config import settings
from app.main import app


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
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "project_ref": "rprgjfvfttxydhbekuoc",
        "database_probe": "probe_unavailable",
        "probe_kind": "probe_unavailable_no_authorized_postgrest_path",
        "deployment_commit": "test-commit-sha",
    }
    assert "server-only-test-key" not in response.text
    assert "supabase.co" not in response.text


def test_database_diagnostic_sanitizes_probe_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://rprgjfvfttxydhbekuoc.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["database_probe"] == "probe_unavailable"
    assert response.json()["project_ref"] == "rprgjfvfttxydhbekuoc"
    assert "secret URL" not in response.text
    assert "server-only-test-key" not in response.text


def test_database_diagnostic_does_not_claim_unrecognized_target(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.invalid")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["project_ref"] is None
    assert response.json()["database_probe"] == "probe_unavailable"



def test_database_diagnostic_never_sends_service_key_to_wrong_supabase_project(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://aaaaaaaaaaaaaaaaaaaa.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["project_ref"] == "aaaaaaaaaaaaaaaaaaaa"
    assert response.json()["database_probe"] == "probe_unavailable"



@pytest.mark.parametrize(
    "url",
    [
        "http://rprgjfvfttxydhbekuoc.supabase.co",
        "https://user@rprgjfvfttxydhbekuoc.supabase.co",
        "https://rprgjfvfttxydhbekuoc.supabase.co/unexpected-path",
        "https://rprgjfvfttxydhbekuoc.supabase.co?redirect=example.invalid",
    ],
)
def test_database_diagnostic_rejects_ambiguous_or_insecure_urls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_service_role_key", "server-only-test-key")

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["project_ref"] is None
    assert response.json()["database_probe"] == "probe_unavailable"
    assert "server-only-test-key" not in response.text


def test_database_diagnostic_requires_trusted_github_actions_identity(client: TestClient) -> None:
    app.dependency_overrides.pop(require_github_actions, None)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 401
