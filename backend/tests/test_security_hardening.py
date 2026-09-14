from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth import _csrf_token, _require_csrf
from app.api.auth import router as auth_router
from app.config import settings
from app.main import app
from app.preferences.router import router as preferences_router


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_settings_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/preferences")
    assert response.status_code == 401


def test_settings_mutation_requires_csrf(client: TestClient) -> None:
    response = client.put("/api/preferences", json={})
    assert response.status_code in {401, 403}


def test_csrf_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_csrf(None, None, "session-token", "https://research.example")
    assert exc.value.status_code == 403


def test_csrf_rejects_mismatched_header_and_cookie() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_csrf("cookie-token", "header-token", "session-token", "https://research.example")
    assert exc.value.status_code == 403


def test_csrf_accepts_signed_session_token() -> None:
    token = "session-token"
    _require_csrf(None, _csrf_token(token), token, None)


def test_production_csrf_rejects_untrusted_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", "https://research.example")
    token = "session-token"
    with pytest.raises(HTTPException) as exc:
        _require_csrf(None, _csrf_token(token), token, "https://evil.example")
    assert exc.value.status_code == 403
    assert "origin" in str(exc.value.detail).lower()


def test_production_csrf_accepts_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", "https://research.example")
    token = "session-token"
    _require_csrf(None, _csrf_token(token), token, "https://research.example")


def test_password_change_requires_csrf(client: TestClient) -> None:
    with patch("app.api.auth.get_user", return_value={"id": "u1", "email": "u1@example.com"}):
        client.cookies.set("mr_access_token", "session-token")
        response = client.post(
            "/api/auth/password/change",
            json={"current_password": "old-password", "new_password": "new-password"},
        )
    assert response.status_code == 403


def test_other_session_revocation_requires_csrf(client: TestClient) -> None:
    client.cookies.set("mr_access_token", "session-token")
    response = client.post("/api/auth/sessions/sign-out-others")
    assert response.status_code == 403


def test_account_deletion_requires_exact_confirmation_and_csrf(client: TestClient) -> None:
    client.cookies.set("mr_access_token", "session-token")
    with patch("app.api.auth.get_user", return_value={"id": "u1", "email": "u1@example.com"}):
        response = client.delete(
            "/api/auth/account",
            json={"confirmation": "delete"},
            headers={"X-CSRF-Token": _csrf_token("session-token")},
        )
    assert response.status_code == 422


def test_github_oidc_rejects_untrusted_event() -> None:
    from app.api.auth import _validate_github_oidc_claims

    claims = {
        "repository": settings.github_oidc_repository,
        "ref": settings.github_oidc_ref,
        "workflow_ref": f"{settings.github_oidc_repository}/{settings.github_oidc_workflow}@{settings.github_oidc_ref}",
        "event_name": "pull_request",
    }
    with pytest.raises(HTTPException) as exc:
        _validate_github_oidc_claims(claims)
    assert exc.value.status_code == 403


def test_github_oidc_rejects_wrong_repository() -> None:
    from app.api.auth import _validate_github_oidc_claims

    claims = {
        "repository": "attacker/research",
        "ref": settings.github_oidc_ref,
        "workflow_ref": f"attacker/research/{settings.github_oidc_workflow}@{settings.github_oidc_ref}",
        "event_name": "push",
    }
    with pytest.raises(HTTPException) as exc:
        _validate_github_oidc_claims(claims)
    assert exc.value.status_code == 403


def test_sensitive_preference_routes_have_csrf_dependencies() -> None:
    routes = {route.path: route for route in preferences_router.routes}
    for path in ("/api/preferences", "/api/preferences/reset", "/api/preferences/data/research-history", "/api/preferences/data/watchlists", "/api/preferences/data/cache"):
        route = routes[path]
        assert any(getattr(dependency.call, "__name__", "") == "_require_csrf" for dependency in route.dependant.dependencies)


def test_sensitive_auth_routes_have_csrf_dependencies() -> None:
    routes = {route.path: route for route in auth_router.routes}
    for path in ("/api/auth/password/change", "/api/auth/sessions/sign-out-others", "/api/auth/sessions/sign-out-all", "/api/auth/account", "/api/auth/logout"):
        route = routes[path]
        assert any(getattr(dependency.call, "__name__", "") == "_require_csrf" for dependency in route.dependant.dependencies)
