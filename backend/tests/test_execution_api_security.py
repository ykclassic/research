from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.api import execution as execution_api
from app.api.auth import UserResponse
from app.main import app
from app.models.execution import ExecutionAuthorization, ExecutionRequest
from app.services.entitlement import FeatureNotEntitledError
from app.services.supabase_data import DataUnavailableError
from tests.test_risk_management import make_dataset, make_features, make_selection
from app.services.risk_management import qualify_position


USER = UserResponse(id="4e8e4b1a-8a0a-4f68-8b34-18e1455a09f4", email="premium@example.test", account_status="active")


def _payload() -> dict:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    return ExecutionRequest(position=position).model_dump(mode="json")


@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _authenticate_with_csrf() -> None:
    app.dependency_overrides[execution_api.get_current_user] = lambda: USER
    app.dependency_overrides[execution_api._require_csrf] = lambda: None


def test_public_execution_request_rejects_client_supplied_approval_fields() -> None:
    position = qualify_position(make_selection(), make_dataset(), make_features(), 10_000)
    with pytest.raises(ValidationError):
        ExecutionRequest(
            position=position,
            authorization=ExecutionAuthorization(
                approved=True,
                approval_id="forged-approval",
            ),
        )


def test_execution_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 401
    assert "authentication" in response.json()["detail"].lower()


def test_execution_endpoint_requires_csrf_for_cookie_session(client: TestClient) -> None:
    app.dependency_overrides[execution_api.get_current_user] = lambda: USER
    client.cookies.set("mr_access_token", "opaque-test-token")

    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 403
    assert "csrf" in response.json()["detail"].lower()


def test_execution_endpoint_rejects_untrusted_origin_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.auth import _require_csrf
    from app.config import settings

    app.dependency_overrides[execution_api.get_current_user] = lambda: USER
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "cors_origins", "https://research.vercel.app")
    client.cookies.set("mr_access_token", "opaque-test-token")
    client.cookies.set("mr_csrf", "matching-csrf")
    response = client.post(
        "/api/execution/order",
        json=_payload(),
        headers={"X-CSRF-Token": "matching-csrf", "Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert "origin" in response.json()["detail"].lower()


def test_non_entitled_user_is_denied_before_execution(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_with_csrf()
    client.cookies.set("mr_access_token", "opaque-test-token")

    def deny(*args, **kwargs):
        raise FeatureNotEntitledError("live_trade_execution", "pro")

    monkeypatch.setattr(execution_api, "require_feature", deny)
    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 403
    assert "not available" in response.json()["detail"].lower()


def test_entitlement_lookup_failure_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_with_csrf()
    client.cookies.set("mr_access_token", "opaque-test-token")

    def unavailable(*args, **kwargs):
        raise DataUnavailableError("test-only backend outage")

    monkeypatch.setattr(execution_api, "require_feature", unavailable)
    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 503
    assert "could not be verified" in response.json()["detail"].lower()
    assert "test-only backend outage" not in response.text


def test_even_entitled_user_cannot_execute_until_approval_store_exists(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _authenticate_with_csrf()
    client.cookies.set("mr_access_token", "opaque-test-token")
    monkeypatch.setattr(
        execution_api,
        "require_feature",
        lambda *args, **kwargs: {"plan_id": "premium", "features": {"live_trade_execution": True}},
    )

    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()
