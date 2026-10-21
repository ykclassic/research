from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

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
VALID_SHA = "4d5eefeb6cd231a7b733db508035fa869814ad7b"


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


def assert_no_network_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("diagnostic must not issue an unverified PostgREST/Auth request")

    monkeypatch.setattr(diagnostics_api.httpx, "get", forbidden)
    monkeypatch.setattr(diagnostics_api.httpx, "request", forbidden)


@pytest.mark.parametrize(
    ("expected_ref", "reason"),
    [
        ("", "expected_target_missing"),
        ("   ", "expected_target_missing"),
        ("not-a-project-ref", "expected_target_invalid"),
        ("AAAAAAAAAAAAAAAAAAAA", "expected_target_invalid"),
    ],
)
def test_missing_or_invalid_expected_target_fails_closed_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, expected_ref: str, reason: str
) -> None:
    configure(monkeypatch, expected_ref=expected_ref)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == reason
    assert response.json()["project_ref"] is None


def test_target_mismatch_fails_before_any_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, url="https://aaaaaaaaaaaaaaaaaaaa.supabase.co")
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "target_mismatch"
    assert response.json()["project_ref"] == "aaaaaaaaaaaaaaaaaaaa"


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "supabase_url_invalid"),
        (" https://rprgjfvfttxydhbekuoc.supabase.co", "supabase_url_invalid"),
        ("http://rprgjfvfttxydhbekuoc.supabase.co", "supabase_url_invalid"),
        ("https://rprgjfvfttxydhbekuoc.supabase.co.evil.invalid", "supabase_url_invalid"),
        ("https://rprgjfvfttxydhbekuoc.supabase.co/path", "supabase_url_invalid"),
        ("https://rprgjfvfttxydhbekuoc.supabase.co?redirect=evil", "supabase_url_invalid"),
        ("https://user@rprgjfvfttxydhbekuoc.supabase.co", "supabase_url_invalid"),
        ("https://rprgjfvfttxydhbekuoc.supabase.co:8443", "supabase_url_invalid"),
        ("https://rprgjfvfttxydhbekuoc.supabase.co:invalid", "supabase_url_invalid"),
        ("https://not-a-project-ref.supabase.co", "supabase_url_invalid"),
        ("https://example.invalid", "supabase_url_invalid"),
        ("not a URL", "supabase_url_invalid"),
    ],
)
def test_malformed_url_fails_closed_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, url: str, reason: str
) -> None:
    configure(monkeypatch, url=url)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == reason
    assert not url or url not in response.text


@pytest.mark.parametrize(
    ("sha_value", "reason"),
    [
        (None, "deployment_identity_missing"),
        ("", "deployment_identity_missing"),
        ("not-a-commit-sha", "deployment_identity_invalid"),
        ("g" * 40, "deployment_identity_invalid"),
        ("a" * 39, "deployment_identity_invalid"),
    ],
)
def test_missing_or_invalid_deployment_identity_fails_without_probe(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sha_value: str | None,
    reason: str,
) -> None:
    configure(monkeypatch)
    if sha_value is None:
        monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    else:
        monkeypatch.setenv("RENDER_GIT_COMMIT", sha_value)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["reason_code"] == reason
    assert payload["deployment_sha"] is None
    assert payload["project_ref"] == EXPECTED_REF
    assert not sha_value or sha_value not in response.text


def test_valid_deployment_identity_still_fails_closed_when_no_authorized_postgrest_probe_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_ref"] == EXPECTED_REF
    assert payload["deployment_sha"] == VALID_SHA
    assert payload["status"] == "failed"
    assert payload["reason_code"] == "probe_unavailable"
    assert "PostgREST" in payload["probe_method"]
    assert "authenticated user JWT" in payload["probe_method"]


@pytest.mark.parametrize("key", ["", "   "])
def test_missing_publishable_key_fails_closed_without_probe(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    configure(monkeypatch, key=key)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["reason_code"] == "publishable_key_missing"


def test_diagnostic_requires_trusted_github_actions_identity(client: TestClient) -> None:
    app.dependency_overrides.pop(require_github_actions, None)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 401


def test_output_contains_only_sanitized_fields_and_valid_utc_timestamp(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_network_probe(monkeypatch)

    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "project_ref", "deployment_sha", "timestamp_utc",
        "probe_method", "status", "reason_code",
    }
    assert payload["timestamp_utc"].endswith("Z")
    datetime.fromisoformat(payload["timestamp_utc"].replace("Z", "+00:00"))
    assert PUBLISHABLE_KEY not in response.text
    assert SERVICE_ROLE_SECRET not in response.text
    assert "supabase.co" not in response.text
    assert "/auth/v1/" not in response.text
    assert "/rest/v1/rpc/" not in response.text
