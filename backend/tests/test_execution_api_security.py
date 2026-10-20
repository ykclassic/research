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


USER = UserResponse(id="4e8e4b1a-8a0a-4f68-8b34-18e1455a09f4", email="premium@example.com", account_status="active")


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



def test_feature_flag_cannot_upgrade_pro_to_premium(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticate_with_csrf()
    client.cookies.set("mr_access_token", "opaque-test-token")
    monkeypatch.setattr(
        execution_api,
        "require_feature",
        lambda *args, **kwargs: {"plan_id": "pro", "features": {"live_trade_execution": True}},
    )

    response = client.post("/api/execution/order", json=_payload())

    assert response.status_code == 403
    assert "premium" in response.json()["detail"].lower()


def _approval_preview() -> dict:
    from datetime import datetime, timedelta, timezone

    return {
        "intent_id": "0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431",
        "request_hash": "a" * 64,
        "account_ref": "server-account",
        "symbol": "BTC/USDT",
        "side": "LONG",
        "quantity": 0.25,
        "entry_price": 65000.0,
        "stop_loss": 64000.0,
        "take_profit": 68000.0,
        "risk_policy_version": "risk-v3",
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
    }


def test_approval_request_rejects_caller_authored_actor_or_snapshot() -> None:
    from app.models.execution import ExecutionApprovalDecisionRequest

    with pytest.raises(ValidationError):
        ExecutionApprovalDecisionRequest(
            decision="APPROVE",
            request_hash="a" * 64,
            actor_user_id="b89e6b8b-9a6c-48cc-8e2b-2c60f3cb6a45",
        )
    with pytest.raises(ValidationError):
        ExecutionApprovalDecisionRequest(
            decision="APPROVE",
            request_hash="a" * 64,
            human_confirmed=True,
        )


def test_approval_preview_requires_authenticated_owner(client: TestClient) -> None:
    response = client.get(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-preview"
    )
    assert response.status_code == 401


def test_approval_decision_requires_csrf(client: TestClient) -> None:
    app.dependency_overrides[execution_api.get_current_user] = lambda: USER
    response = client.post(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval",
        json={"decision": "APPROVE", "request_hash": "a" * 64, "challenge": "x" * 64},
    )
    assert response.status_code == 403


def test_changed_proposal_hash_cannot_be_approved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    _authenticate_with_csrf()
    preview = _approval_preview()
    monkeypatch.setattr(
        execution_api, "get_execution_intent_approval_preview",
        lambda **kwargs: preview,
    )
    recorded = []
    monkeypatch.setattr(execution_api, "record_execution_approval", lambda **kwargs: recorded.append(kwargs))
    challenge_response = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval-challenge",
        json={"decision": "APPROVE", "request_hash": preview["request_hash"]},
    )
    assert challenge_response.status_code == 200
    response = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval",
        json={"decision": "APPROVE", "request_hash": "f" * 64,
              "challenge": challenge_response.json()["challenge"]},
    )
    assert response.status_code == 403
    assert recorded == []


def test_approval_actor_and_snapshot_are_derived_from_session_and_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID
    from types import SimpleNamespace

    _authenticate_with_csrf()
    preview = _approval_preview()
    monkeypatch.setattr(
        execution_api, "get_execution_intent_approval_preview",
        lambda **kwargs: preview,
    )
    calls = []

    def record(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(approval_id=UUID("e3f0fd88-1770-4a52-a7c2-c6a35d7b26d0"))

    monkeypatch.setattr(execution_api, "record_execution_approval", record)
    challenge_response = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval-challenge",
        json={"decision": "APPROVE", "request_hash": preview["request_hash"]},
    )
    assert challenge_response.status_code == 200
    response = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval",
        json={"decision": "APPROVE", "request_hash": preview["request_hash"],
              "challenge": challenge_response.json()["challenge"]},
    )
    assert response.status_code == 200
    assert len(calls) == 1
    call = calls[0]
    assert call["user_id"] == UUID(USER.id)
    assert call["actor_user_id"] == UUID(USER.id)
    assert call["approval_snapshot"]["account_ref"] == "server-account"
    assert call["approval_snapshot"]["symbol"] == "BTC/USDT"
    assert call["approval_snapshot"]["risk_policy_version"] == "risk-v3"
    assert call["approval_snapshot"]["human_confirmed"] is True
    assert "actor_user_id" not in response.json()


def test_execution_router_exposes_no_unreviewed_submission_paths() -> None:
    reachable = {
        route.path for route in app.routes
        if getattr(route, "path", "").startswith("/api/execution")
    }
    assert reachable == {
        "/api/execution/order",
        "/api/execution/intents/{intent_id}/approval-preview",
        "/api/execution/intents/{intent_id}/approval-challenge",
        "/api/execution/intents/{intent_id}/approval",
    }


def test_approval_challenge_is_bound_to_action_and_authenticated_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID

    _authenticate_with_csrf()
    preview = _approval_preview()
    monkeypatch.setattr(
        execution_api, "get_execution_intent_approval_preview",
        lambda **kwargs: preview,
    )
    challenge_response = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval-challenge",
        json={"decision": "APPROVE", "request_hash": preview["request_hash"]},
    )
    assert challenge_response.status_code == 200
    token = challenge_response.json()["challenge"]

    # A challenge for APPROVE cannot authorize REJECT, even for the same user.
    mismatch = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval",
        json={"decision": "REJECT", "request_hash": preview["request_hash"], "challenge": token},
    )
    assert mismatch.status_code == 403

    # A challenge minted for user A cannot be used by user B.
    other_user = UserResponse(
        id="0c8a831d-2b89-4d32-a1d8-9f5f9d7b5e03",
        email="other@example.com",
        account_status="active",
    )
    app.dependency_overrides[execution_api.get_current_user] = lambda: other_user
    foreign = client.post(
        f"/api/execution/intents/{preview['intent_id']}/approval",
        json={"decision": "APPROVE", "request_hash": preview["request_hash"], "challenge": token},
    )
    assert foreign.status_code == 403
