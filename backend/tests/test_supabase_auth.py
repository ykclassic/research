from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.supabase_auth import (
    AuthEmailNotConfirmedError,
    AuthInvalidCredentialsError,
    AuthUnavailableError,
)


client = TestClient(app)


def test_register_does_not_create_session_cookie():
    client.cookies.clear()
    with patch("app.api.auth.sign_up") as sign_up:
        sign_up.return_value = {
            "user": {
                "id": "u1",
                "email": "user@example.com",
                "created_at": "2026-01-01T00:00:00Z",
            },
            "access_token": "registration-token-that-must-not-be-used",
        }
        response = client.post(
            "/api/auth/register",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 201
    assert response.json()["id"] == "u1"
    assert "mr_access_token" not in response.cookies
    assert "mr_csrf" not in response.cookies


def test_login_creates_session_cookie():
    client.cookies.clear()
    with patch("app.api.auth.sign_in") as sign_in:
        sign_in.return_value = {
            "user": {
                "id": "u1",
                "email": "user@example.com",
                "created_at": "2026-01-01T00:00:00Z",
            },
            "access_token": "login-token",
        }
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == "u1"
    assert "mr_access_token" in response.cookies
    assert "mr_csrf" in response.cookies


def test_login_rejects_invalid_credentials():
    client.cookies.clear()
    with patch(
        "app.api.auth.sign_in",
        side_effect=AuthInvalidCredentialsError("Invalid login credentials"),
    ):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrongpass"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_reports_unconfirmed_email():
    client.cookies.clear()
    with patch(
        "app.api.auth.sign_in",
        side_effect=AuthEmailNotConfirmedError("Email not confirmed"),
    ):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Email address has not been confirmed."


def test_login_reports_auth_service_unavailable():
    client.cookies.clear()
    with patch(
        "app.api.auth.sign_in",
        side_effect=AuthUnavailableError("Authentication service is unavailable."),
    ):
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "password123"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service is temporarily unavailable."


def test_me_requires_authentication():
    client.cookies.clear()
    response = client.get("/api/auth/me")
    assert response.status_code == 401
