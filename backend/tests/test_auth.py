from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_register_creates_auth_cookies_and_current_user(client):
    user = {
        "id": "u1",
        "email": "user@example.com",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch("app.api.auth.sign_up", return_value={"user": user, "access_token": "token"}), patch(
        "app.api.auth.get_user", return_value=user
    ):
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "correct-horse-battery"},
        )
        assert response.status_code == 201
        assert response.json() == user
        assert "mr_access_token" in response.cookies
        assert "mr_csrf" in response.cookies

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == user


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
