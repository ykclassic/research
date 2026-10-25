from __future__ import annotations

import ast
from pathlib import Path

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
def client(monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        execution_api,
        "require_feature",
        lambda *args, **kwargs: {
            "plan_id": "premium",
            "features": {"live_trade_execution": True},
        },
    )
    with TestClient(app) as test_client:
        test_client.cookies.set("mr_access_token", "opaque-test-token")
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


@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-challenge",
            {"decision": "APPROVE", "request_hash": "a" * 64},
        ),
        (
            "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval",
            {"decision": "APPROVE", "request_hash": "a" * 64, "challenge": "invalid"},
        ),
    ],
)
@pytest.mark.parametrize(
    "entitlement",
    [
        {"plan_id": "free", "features": {"live_trade_execution": False}},
        {"plan_id": "pro", "features": {"live_trade_execution": True}},
        {"plan_id": "premium", "features": {}},
        {"plan_id": "premium", "features": {"live_trade_execution": False}},
    ],
)
def test_approval_mutations_require_current_premium_feature(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str, payload: dict, entitlement: dict
) -> None:
    _authenticate_with_csrf()
    monkeypatch.setattr(execution_api, "require_feature", lambda *args, **kwargs: entitlement)
    response = client.post(path, json=payload)
    assert response.status_code == 403
    assert "not available" in response.json()["detail"].lower() or "premium" in response.json()["detail"].lower()

@pytest.mark.parametrize(
    "path,payload",
    [
        (
            "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-challenge",
            {"decision": "APPROVE", "request_hash": "a" * 64},
        ),
        (
            "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval",
            {"decision": "APPROVE", "request_hash": "a" * 64, "challenge": "invalid"},
        ),
    ],
)
def test_approval_mutations_fail_closed_when_entitlement_service_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, path: str, payload: dict
) -> None:
    _authenticate_with_csrf()
    def unavailable(*args, **kwargs):
        raise DataUnavailableError("private provider failure")
    monkeypatch.setattr(execution_api, "require_feature", unavailable)
    response = client.post(path, json=payload)
    assert response.status_code == 503
    assert "could not be verified" in response.json()["detail"].lower()
    assert "private provider failure" not in response.text


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
    with pytest.raises(ValidationError):
        ExecutionApprovalDecisionRequest(
            decision="APPROVE",
            request_hash="a" * 64,
            user_id="b89e6b8b-9a6c-48cc-8e2b-2c60f3cb6a45",
        )


def test_approval_preview_requires_authenticated_owner(client: TestClient) -> None:
    response = client.get(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-preview"
    )
    assert response.status_code == 401


def test_approval_preview_scopes_lookup_to_verified_session_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID
    from app.services.supabase_data import DataRequestError

    _authenticate_with_csrf()
    observed = []

    def owner_scoped_preview(*, user_id, intent_id):
        observed.append((user_id, intent_id))
        if user_id != UUID(USER.id):
            raise DataRequestError("not found")
        return _approval_preview()

    monkeypatch.setattr(execution_api, "get_execution_intent_approval_preview", owner_scoped_preview)
    response = client.get(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-preview"
    )

    assert response.status_code == 200
    assert observed == [(UUID(USER.id), UUID("0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431"))]


def test_approval_decision_requires_csrf(client: TestClient) -> None:
    app.dependency_overrides[execution_api.get_current_user] = lambda: USER
    response = client.post(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval",
        json={"decision": "APPROVE", "request_hash": "a" * 64, "challenge": "x" * 64},
    )
    assert response.status_code == 403


def test_foreign_intent_cannot_be_challenged_by_another_authenticated_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import UUID
    from app.services.supabase_data import DataRequestError

    other_user = UserResponse(
        id="0c8a831d-2b89-4d32-a1d8-9f5f9d7b5e03",
        email="other@example.com",
        account_status="active",
    )
    app.dependency_overrides[execution_api.get_current_user] = lambda: other_user
    app.dependency_overrides[execution_api._require_csrf] = lambda: None
    observed = []
    recorded = []

    def owner_scoped_preview(*, user_id, intent_id):
        observed.append((user_id, intent_id))
        raise DataRequestError("not found")

    monkeypatch.setattr(execution_api, "get_execution_intent_approval_preview", owner_scoped_preview)
    monkeypatch.setattr(execution_api, "record_execution_approval", lambda **kwargs: recorded.append(kwargs))
    response = client.post(
        "/api/execution/intents/0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431/approval-challenge",
        json={"decision": "APPROVE", "request_hash": "a" * 64},
    )

    assert response.status_code == 404
    assert observed == [
        (UUID(other_user.id), UUID("0d64c25d-a3d2-46c6-9ed2-ff1a7c3d8431"))
    ]
    assert recorded == []


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
    monkeypatch.setattr(
        execution_api, "register_execution_approval_challenge",
        lambda **kwargs: None,
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
    monkeypatch.setattr(
        execution_api, "register_execution_approval_challenge",
        lambda **kwargs: None,
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
    assert isinstance(call["challenge_jti"], str) and call["challenge_jti"]
    assert call["approval_snapshot"]["account_ref"] == "server-account"
    assert call["approval_snapshot"]["symbol"] == "BTC/USDT"
    assert call["approval_snapshot"]["risk_policy_version"] == "risk-v3"
    assert "human_confirmed" not in call["approval_snapshot"]
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
    monkeypatch.setattr(
        execution_api, "register_execution_approval_challenge",
        lambda **kwargs: None,
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


def test_repository_has_no_alternate_order_submission_call_paths() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    execution_module = (app_root / "services" / "execution.py").resolve()
    violations = []

    for source_path in app_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.services.execution":
                if any(alias.name == "execute_order" for alias in node.names):
                    if source_path.resolve() != execution_module:
                        violations.append(f"{source_path}: imports execute_order")
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            calls_execute_order = (
                isinstance(function, ast.Name) and function.id == "execute_order"
            ) or (
                isinstance(function, ast.Attribute) and function.attr == "execute_order"
            )
            calls_broker_submission = (
                isinstance(function, ast.Attribute) and function.attr == "submit_order"
            )
            if source_path.resolve() != execution_module and (
                calls_execute_order or calls_broker_submission
            ):
                violations.append(f"{source_path}:{node.lineno}: order submission call")

    assert violations == [], "Alternate execution paths found: " + "; ".join(violations)
