import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_database_path", str(tmp_path / "auth.db"))
    with TestClient(app) as test_client:
        yield test_client


def test_register_creates_session_and_current_user(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"
    assert "mr_session" in response.cookies
    assert "mr_csrf" in response.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_duplicate_registration_is_rejected(client):
    payload = {"email": "user@example.com", "password": "correct-horse-battery"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 409


def test_login_rejects_invalid_password(client):
    payload = {"email": "user@example.com", "password": "correct-horse-battery"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_logout_requires_csrf_and_revokes_session(client):
    payload = {"email": "user@example.com", "password": "correct-horse-battery"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    csrf = client.cookies.get("mr_csrf")
    without_csrf = client.post("/api/auth/logout")
    assert without_csrf.status_code == 403

    response = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_market_api_requires_authentication(client):
    response = client.get("/api/market/quotes")
    assert response.status_code == 401
