from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth import _validate_github_oidc_claims
from app.config import settings
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_register_does_not_create_auth_session(client):
    user = {
        "id": "u1",
        "email": "user@example.com",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch(
        "app.api.auth.sign_up",
        return_value={"user": user, "access_token": "token"},
    ) as sign_up, patch("app.api.auth.get_user") as get_user:
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )

    assert response.status_code == 201
    assert response.json() == user
    assert response.cookies.get("mr_access_token") is None
    assert response.cookies.get("mr_csrf") is None
    sign_up.assert_called_once_with("user@example.com", "correct-horse-battery")
    get_user.assert_not_called()

    me = client.get("/api/auth/me")
    assert me.status_code == 401


def test_duplicate_registration_is_rejected(client):
    from app.services.supabase_auth import AuthServiceError

    with patch(
        "app.api.auth.sign_up",
        side_effect=AuthServiceError("User already registered"),
    ):
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )

    assert response.status_code == 409


def test_login_creates_auth_session(client):
    user = {
        "id": "u1",
        "email": "user@example.com",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch(
        "app.api.auth.sign_in",
        return_value={"user": user, "access_token": "token"},
    ), patch("app.api.auth.get_user", return_value=user):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )

        assert response.status_code == 200
        assert response.json() == user
        assert response.cookies.get("mr_access_token") == "token"
        assert response.cookies.get("mr_csrf")

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == user


def test_login_rejects_invalid_password(client):
    from app.services.supabase_auth import AuthServiceError

    with patch(
        "app.api.auth.sign_in",
        side_effect=AuthServiceError("Invalid login credentials"),
    ):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 401


def test_logout_requires_csrf_and_clears_session(client):
    user = {
        "id": "u1",
        "email": "user@example.com",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch("app.api.auth.sign_in", return_value={"user": user, "access_token": "token"}), patch(
        "app.api.auth.get_user", return_value=user
    ), patch("app.api.auth.sign_out") as sign_out:
        login = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )
        assert login.status_code == 200

        csrf = client.cookies.get("mr_csrf")
        without_csrf = client.post("/api/auth/logout")
        assert without_csrf.status_code == 403

        response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert response.status_code == 204
        sign_out.assert_called_once_with("token")
        assert client.cookies.get("mr_access_token") is None


def test_market_api_requires_authentication(client):
    response = client.get("/api/market/quotes")
    assert response.status_code == 401


def _oidc_claims(event_name: str, workflow: str | None = None, ref: str | None = None) -> dict[str, str]:
    workflow = workflow or settings.github_oidc_workflow
    return {
        "repository": settings.github_oidc_repository,
        "ref": ref or settings.github_oidc_ref,
        "workflow_ref": f"{settings.github_oidc_repository}/{workflow}@{settings.github_oidc_ref}",
        "event_name": event_name,
    }


def test_production_market_workflow_push_event_is_trusted():
    _validate_github_oidc_claims(_oidc_claims("push"))


@pytest.mark.parametrize("event_name", ["schedule", "workflow_dispatch"])
def test_existing_production_oidc_events_remain_trusted(event_name):
    _validate_github_oidc_claims(_oidc_claims(event_name))


def test_push_from_regime_workflow_is_rejected():
    claims = _oidc_claims("push", workflow=".github/workflows/production-regime-verification.yml")
    with pytest.raises(HTTPException, match="event is not trusted"):
        _validate_github_oidc_claims(claims)


def test_push_from_untrusted_workflow_is_rejected():
    claims = _oidc_claims("push", workflow=".github/workflows/untrusted.yml")
    with pytest.raises(HTTPException, match="workflow is not trusted"):
        _validate_github_oidc_claims(claims)


def test_trusted_workflow_on_non_main_ref_is_rejected():
    claims = _oidc_claims("push", ref="refs/heads/feature/test")
    with pytest.raises(HTTPException, match="ref is not trusted"):
        _validate_github_oidc_claims(claims)
