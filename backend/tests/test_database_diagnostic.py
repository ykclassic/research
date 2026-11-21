from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from app.api.auth import require_github_actions
from app.config import settings
from app.main import app

EXPECTED_REF = "rprgjfvfttxydhbekuoc"
EXPECTED_URL = f"https://{EXPECTED_REF}.supabase.co"
VALID_SHA = "a" * 40
PUBLISHABLE_KEY = "sb_publishable_test"
SERVICE_ROLE_SECRET = "service-role-test-secret"


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


@pytest.fixture
def client():
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[require_github_actions] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


def configure(monkeypatch: pytest.MonkeyPatch, *, url: str = EXPECTED_URL, expected_ref: str = EXPECTED_REF, service_key: str = SERVICE_ROLE_SECRET) -> None:
    monkeypatch.setattr(settings, "supabase_url", url)
    monkeypatch.setattr(settings, "supabase_expected_production_project_ref", expected_ref)
    monkeypatch.setattr(settings, "supabase_service_role_key", service_key)


def assert_no_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import diagnostics

    monkeypatch.setattr(diagnostics, "service_request", lambda *args, **kwargs: pytest.fail("database probe must not run"))


def test_database_diagnostic_uses_only_fixed_read_only_service_role_query(client, monkeypatch):
    from app.api import diagnostics

    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    calls = []

    def probe(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return _FakeResponse([{"id": "free"}])

    monkeypatch.setattr(diagnostics, "service_request", probe)
    response = client.get("/internal/diagnostics/database")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_ref"] == EXPECTED_REF
    assert payload["deployment_sha"] == VALID_SHA
    assert payload["status"] == "passed"
    assert payload["reason_code"] is None
    assert payload["probe_method"] == diagnostics.PROBE_METHOD
    assert calls == [("GET", "billing_plans", {"params": {"select": "id", "limit": "1"}})]
    assert SERVICE_ROLE_SECRET not in response.text
    assert PUBLISHABLE_KEY not in response.text
    assert "supabase.co" not in response.text


@pytest.mark.parametrize(("expected_ref", "reason"), [
    ("", "expected_target_missing"),
    (" ", "expected_target_missing"),
    ("invalid-ref", "expected_target_invalid"),
    ("A" * 20, "expected_target_invalid"),
])
def test_missing_or_invalid_expected_target_fails_closed(client, monkeypatch, expected_ref, reason):
    configure(monkeypatch, expected_ref=expected_ref)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.status_code == 200
    assert response.json()["reason_code"] == reason
    assert response.json()["status"] == "failed"


@pytest.mark.parametrize("url", [
    "",
    " http://rprgjfvfttxydhbekuoc.supabase.co",
    "http://rprgjfvfttxydhbekuoc.supabase.co",
    "https://rprgjfvfttxydhbekuoc.supabase.co.evil.invalid",
    "https://rprgjfvfttxydhbekuoc.supabase.co/path",
    "https://rprgjfvfttxydhbekuoc.supabase.co?redirect=evil",
    "https://user@rprgjfvfttxydhbekuoc.supabase.co",
    "https://rprgjfvfttxydhbekuoc.supabase.co:8443",
    "https://not-a-project-ref.supabase.co",
    "https://example.invalid",
])
def test_invalid_or_ambiguous_supabase_url_fails_before_probe(client, monkeypatch, url):
    configure(monkeypatch, url=url)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.status_code == 200
    assert response.json()["reason_code"] == "supabase_url_invalid"
    assert response.json()["project_ref"] is None
    assert url not in response.text if url else True


def test_target_mismatch_fails_before_probe(client, monkeypatch):
    configure(monkeypatch, url="https://aaaaaaaaaaaaaaaaaaaa.supabase.co")
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.json()["reason_code"] == "target_mismatch"
    assert response.json()["status"] == "failed"


@pytest.mark.parametrize(("sha", "reason"), [
    ("", "deployment_identity_missing"),
    ("not-a-sha", "deployment_identity_invalid"),
    ("g" * 40, "deployment_identity_invalid"),
    ("a" * 39, "deployment_identity_invalid"),
])
def test_invalid_deployment_identity_fails_before_probe(client, monkeypatch, sha, reason):
    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", sha)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.json()["reason_code"] == reason
    assert response.json()["deployment_sha"] is None


def test_missing_deployment_identity_fails_before_probe(client, monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.json()["reason_code"] == "deployment_identity_missing"


def test_missing_service_role_key_fails_before_probe(client, monkeypatch):
    configure(monkeypatch, service_key="")
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    assert_no_probe(monkeypatch)
    response = client.get("/internal/diagnostics/database")
    assert response.json()["reason_code"] == "service_role_key_missing"


def test_probe_failure_is_sanitized(client, monkeypatch):
    from app.api import diagnostics

    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)

    def fail(*args, **kwargs):
        raise RuntimeError("private URL and credential must not leak")

    monkeypatch.setattr(diagnostics, "service_request", fail)
    response = client.get("/internal/diagnostics/database")
    assert response.status_code == 200
    assert response.json()["reason_code"] == "probe_failed"
    assert "private URL" not in response.text
    assert SERVICE_ROLE_SECRET not in response.text


def test_non_list_probe_response_is_failed(client, monkeypatch):
    from app.api import diagnostics

    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    monkeypatch.setattr(diagnostics, "service_request", lambda *args, **kwargs: _FakeResponse({"unexpected": True}))
    response = client.get("/internal/diagnostics/database")
    assert response.json()["reason_code"] == "probe_response_invalid"


def test_diagnostic_requires_trusted_github_actions_identity(client):
    app.dependency_overrides.pop(require_github_actions, None)
    response = client.get("/internal/diagnostics/database")
    assert response.status_code == 401


def test_diagnostic_output_is_sanitized_and_timestamp_is_utc(client, monkeypatch):
    from app.api import diagnostics

    configure(monkeypatch)
    monkeypatch.setenv("RENDER_GIT_COMMIT", VALID_SHA)
    monkeypatch.setattr(diagnostics, "service_request", lambda *args, **kwargs: _FakeResponse([]))
    response = client.get("/internal/diagnostics/database")
    payload = response.json()
    assert set(payload) == {"project_ref", "deployment_sha", "timestamp_utc", "probe_method", "status", "reason_code"}
    assert payload["timestamp_utc"].endswith("Z")
    datetime.fromisoformat(payload["timestamp_utc"].replace("Z", "+00:00"))
    assert SERVICE_ROLE_SECRET not in response.text
    assert "supabase.co" not in response.text
