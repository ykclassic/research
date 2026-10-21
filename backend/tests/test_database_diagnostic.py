from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.api import diagnostics as diagnostics_api
from app.api.auth import require_github_actions
from app.config import settings
from app.main import app
from app.services.supabase_data import DataUnavailableError

EXPECTED_URL = "https://rprgjfvfttxydhbekuoc.supabase.co"
SECRET = "server-only-test-key"


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    app.dependency_overrides[require_github_actions] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def configure(monkeypatch: pytest.MonkeyPatch, url: str, key: str = SECRET) -> None:
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_service_role_key", key)


def test_database_diagnostic_reports_only_sanitized_target_and_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, EXPECTED_URL)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "test-commit-sha")
    calls = []

    def probe(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return [{"id": "this-row-must-not-be-returned"}]

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
    assert SECRET not in response.text
    assert "supabase.co" not in response.text
    assert "this-row-must-not-be-returned" not in response.text


def test_database_diagnostic_sanitizes_known_probe_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, EXPECTED_URL)

    def fail(*args, **kwargs):
        raise DataUnavailableError("secret URL and credentials must not be returned")

    monkeypatch.setattr(diagnostics_api, "service_request", fail)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["database_probe"] == "failed"
    assert response.json()["project_ref"] == "rprgjfvfttxydhbekuoc"
    assert "secret URL" not in response.text
    assert SECRET not in response.text


def test_database_diagnostic_sanitizes_unexpected_probe_exception(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, EXPECTED_URL)
    monkeypatch.setattr(
        diagnostics_api,
        "service_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sensitive provider details")),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["database_probe"] == "failed"
    assert "sensitive provider details" not in response.text
    assert SECRET not in response.text


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("", SECRET),
        (EXPECTED_URL, ""),
        (EXPECTED_URL, "   "),
        ("   ", SECRET),
    ],
)
def test_database_diagnostic_missing_or_blank_configuration_never_probes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str, key: str
) -> None:
    configure(monkeypatch, url, key)
    monkeypatch.setattr(
        diagnostics_api,
        "service_request",
        lambda *args, **kwargs: pytest.fail("probe must not run without complete configuration"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["database_probe"] == "not_configured"
    assert SECRET not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "http://rprgjfvfttxydhbekuoc.supabase.co",
        "https://rprgjfvfttxydhbekuoc.supabase.co.evil.invalid",
        "https://rprgjfvfttxydhbekuoc.supabase.co/path",
        "https://rprgjfvfttxydhbekuoc.supabase.co?redirect=evil",
        "https://user@rprgjfvfttxydhbekuoc.supabase.co",
        "https://rprgjfvfttxydhbekuoc.supabase.co:8443",
        "https://rprgjfvfttxydhbekuoc.supabase.co:invalid",
        "https://not-a-project-ref.supabase.co",
        "https://aaaaaaaaaaaaaaaaaaaa.supabase.co",
        "https://example.invalid",
        "not a URL",
    ],
)
def test_database_diagnostic_rejects_malformed_or_unexpected_target_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    configure(monkeypatch, url)
    monkeypatch.setattr(
        diagnostics_api,
        "service_request",
        lambda *args, **kwargs: pytest.fail("untrusted or malformed target must never be probed"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["project_ref"] is None or response.json()["project_ref"] != "rprgjfvfttxydhbekuoc"
    assert response.json()["database_probe"] == "failed"
    assert SECRET not in response.text
    assert url not in response.text


def test_database_diagnostic_requires_trusted_github_actions_identity(client: TestClient) -> None:
    app.dependency_overrides.pop(require_github_actions, None)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 401
