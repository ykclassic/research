from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
import pytest

from app.api import diagnostics as diagnostics_api
from app.api.auth import require_github_actions
from app.config import settings
from app.main import app

EXPECTED_URL = "https://rprgjfvfttxydhbekuoc.supabase.co"
EXPECTED_REF = "rprgjfvfttxydhbekuoc"
PUBLISHABLE_KEY = "publishable-test-key"
SERVICE_ROLE_SECRET = "service-role-secret-must-never-be-used"


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    app.dependency_overrides[require_github_actions] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def configure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    url: str = EXPECTED_URL,
    key: str = PUBLISHABLE_KEY,
    expected_ref: str = EXPECTED_REF,
) -> None:
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_publishable_key", key)
    monkeypatch.setattr(settings, "supabase_service_role_key", SERVICE_ROLE_SECRET)
    monkeypatch.setattr(settings, "supabase_expected_production_project_ref", expected_ref)


def successful_response():
    return SimpleNamespace(status_code=200, text='{"sensitive":"body must not be returned"}')


def test_database_diagnostic_uses_publishable_key_and_only_read_only_auth_settings_get(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    sha = "4d5eefeb6cd231a7b733db508035fa869814ad7b"
    monkeypatch.setenv("RENDER_GIT_COMMIT", sha)
    calls = []

    def probe(url, **kwargs):
        calls.append((url, kwargs))
        return successful_response()

    monkeypatch.setattr(diagnostics_api.httpx, "get", probe)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_ref"] == EXPECTED_REF
    assert payload["deployment_sha"] == sha
    assert payload["probe_method"] == "GET /auth/v1/settings (publishable key; read-only)"
    assert payload["status"] == "passed"
    assert payload["reason_code"] == "probe_succeeded"
    assert payload["timestamp_utc"].endswith("Z")
    datetime.fromisoformat(payload["timestamp_utc"].replace("Z", "+00:00"))
    assert calls == [(
        f"{EXPECTED_URL}/auth/v1/settings",
        {"headers": {"apikey": PUBLISHABLE_KEY}, "timeout": settings.http_timeout_seconds},
    )]
    assert SERVICE_ROLE_SECRET not in response.text
    assert PUBLISHABLE_KEY not in response.text
    assert "supabase.co" not in response.text
    assert "sensitive" not in response.text
    assert "/rest/v1/rpc/" not in response.text


@pytest.mark.parametrize(
    ("expected_ref", "reason"),
    [
        ("", "expected_target_missing"),
        ("   ", "expected_target_missing"),
        ("not-a-project-ref", "expected_target_invalid"),
        ("AAAAAAAAAAAAAAAAAAAA", "expected_target_invalid"),
    ],
)
def test_missing_or_invalid_expected_target_fails_closed_without_network_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, expected_ref: str, reason: str
) -> None:
    configure(monkeypatch, expected_ref=expected_ref)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("must not probe without a valid explicit expected target"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == reason
    assert response.json()["project_ref"] is None


def test_target_mismatch_never_sends_publishable_key_to_other_project(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    other_url = "https://aaaaaaaaaaaaaaaaaaaa.supabase.co"
    configure(monkeypatch, url=other_url)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("target mismatch must stop before any network call"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "target_mismatch"
    assert response.json()["project_ref"] == "aaaaaaaaaaaaaaaaaaaa"
    assert PUBLISHABLE_KEY not in response.text
    assert other_url not in response.text


@pytest.mark.parametrize(
    "url",
    [
        "",
        " https://rprgjfvfttxydhbekuoc.supabase.co",
        "http://rprgjfvfttxydhbekuoc.supabase.co",
        "https://rprgjfvfttxydhbekuoc.supabase.co.evil.invalid",
        "https://rprgjfvfttxydhbekuoc.supabase.co/path",
        "https://rprgjfvfttxydhbekuoc.supabase.co?redirect=evil",
        "https://user@rprgjfvfttxydhbekuoc.supabase.co",
        "https://rprgjfvfttxydhbekuoc.supabase.co:8443",
        "https://rprgjfvfttxydhbekuoc.supabase.co:invalid",
        "https://not-a-project-ref.supabase.co",
        "https://example.invalid",
        "not a URL",
    ],
)
def test_malformed_or_unexpected_url_fails_closed_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    configure(monkeypatch, url=url)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("malformed URL must never be probed"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "supabase_url_invalid"
    assert not url or url not in response.text


@pytest.mark.parametrize("key", ["", "   "])
def test_missing_publishable_key_fails_closed_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    configure(monkeypatch, key=key)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("must not probe without a publishable key"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "publishable_key_missing"


@pytest.mark.parametrize("status_code", [401, 403])
def test_probe_authorization_failure_is_sanitized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            status_code=status_code, text="private provider response with secret"
        ),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "probe_authorization_failed"
    assert "private provider response" not in response.text
    assert "secret" not in response.text
    assert PUBLISHABLE_KEY not in response.text


@pytest.mark.parametrize("status_code", [300, 404, 429, 500, 503])
def test_non_success_probe_status_fails_without_exposing_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=status_code, text="provider secret detail"),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "probe_http_error"
    assert "provider secret detail" not in response.text


def test_network_error_is_sanitized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)

    def fail(*args, **kwargs):
        raise httpx.ConnectError("secret host and credentials")

    monkeypatch.setattr(diagnostics_api.httpx, "get", fail)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "probe_unavailable"
    assert "secret host" not in response.text
    assert PUBLISHABLE_KEY not in response.text
    assert SERVICE_ROLE_SECRET not in response.text


def test_unexpected_exception_is_sanitized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        diagnostics_api.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private exception text")),
    )

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "probe_unavailable"
    assert "private exception text" not in response.text


def test_invalid_deployment_sha_is_not_echoed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "secret-environment-value")
    monkeypatch.setattr(diagnostics_api.httpx, "get", lambda *args, **kwargs: successful_response())

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["deployment_sha"] is None
    assert "secret-environment-value" not in response.text


def test_diagnostic_requires_trusted_github_actions_identity(client: TestClient) -> None:
    app.dependency_overrides.pop(require_github_actions, None)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 401


def test_probe_never_uses_write_methods_or_execution_rpc_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    calls = []

    def probe(url, **kwargs):
        calls.append((url, kwargs))
        return successful_response()

    monkeypatch.setattr(diagnostics_api.httpx, "get", probe)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.endswith("/auth/v1/settings")
    assert kwargs["headers"] == {"apikey": PUBLISHABLE_KEY}
    assert "json" not in kwargs
    assert "params" not in kwargs
    assert "/rpc/" not in url
