from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.auth import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, UserResponse, get_current_user
from app.main import app


USER = UserResponse(
    id="u1",
    email="user@example.com",
    created_at="2026-01-01T00:00:00Z",
)


@pytest.fixture()
def client():
    app.dependency_overrides[get_current_user] = lambda: USER
    with TestClient(app) as test_client:
        test_client.cookies.set(SESSION_COOKIE, "access-token")
        test_client.cookies.set(CSRF_COOKIE, "csrf-token")
        test_client.headers[CSRF_HEADER] = "csrf-token"
        yield test_client
    app.dependency_overrides.clear()


def test_get_watchlists_returns_default_workspace(client):
    watchlists = [{
        "id": "w1",
        "user_id": "u1",
        "name": "My Watchlist",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "watchlist_items": [],
    }]
    with patch("app.api.watchlists.get_or_create_default_watchlist", return_value=watchlists) as fetch:
        response = client.get("/api/watchlists")

    assert response.status_code == 200
    assert response.json() == {"watchlists": watchlists}
    fetch.assert_called_once_with("access-token", "u1")


def test_create_watchlist_requires_csrf(client):
    client.cookies.delete(CSRF_COOKIE)
    client.headers.pop(CSRF_HEADER, None)
    response = client.post("/api/watchlists", json={"name": "Crypto"})
    assert response.status_code == 403


def test_create_watchlist_normalizes_name(client):
    created = {"id": "w2", "user_id": "u1", "name": "Crypto Research"}
    with patch("app.api.watchlists.create_watchlist", return_value=created) as create:
        response = client.post("/api/watchlists", json={"name": "  Crypto   Research  "})

    assert response.status_code == 201
    assert response.json() == created
    create.assert_called_once_with("access-token", "u1", "Crypto Research")


def test_rename_watchlist(client):
    renamed = {"id": "w1", "user_id": "u1", "name": "Forex"}
    with patch("app.api.watchlists.update_watchlist", return_value=renamed) as update:
        response = client.patch("/api/watchlists/w1", json={"name": "Forex"})

    assert response.status_code == 200
    assert response.json() == renamed
    update.assert_called_once_with("access-token", "u1", "w1", "Forex")


def test_delete_watchlist(client):
    with patch("app.api.watchlists.delete_watchlist") as delete:
        response = client.delete("/api/watchlists/w1")

    assert response.status_code == 204
    delete.assert_called_once_with("access-token", "u1", "w1")


def test_add_symbol_rejects_unsupported_symbol(client):
    response = client.post("/api/watchlists/w1/symbols", json={"symbol": "NOT-A-SYMBOL"})
    assert response.status_code == 400
    assert "Unsupported symbol" in response.json()["detail"]


def test_add_symbol_normalizes_supported_symbol(client):
    item = {"id": "i1", "watchlist_id": "w1", "symbol": "BTC/USD"}
    with patch("app.api.watchlists.add_symbol", return_value=item) as add:
        response = client.post("/api/watchlists/w1/symbols", json={"symbol": "btc/usd"})

    assert response.status_code == 201
    assert response.json() == item
    add.assert_called_once_with("access-token", "u1", "w1", "BTC/USD")


def test_remove_symbol_normalizes_supported_symbol(client):
    with patch("app.api.watchlists.remove_symbol") as remove:
        response = client.delete("/api/watchlists/w1/symbols/BTC%2FUSD")

    assert response.status_code == 204
    remove.assert_called_once_with("access-token", "u1", "w1", "BTC/USD")
