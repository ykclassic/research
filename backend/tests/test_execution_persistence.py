from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services import execution_persistence
from app.services.supabase_data import DataRequestError


class _Response:
    def __init__(self, value):
        self._value = value

    def json(self):
        return self._value


def test_intent_creation_uses_canonical_database_hash(monkeypatch) -> None:
    user_id = uuid4()
    intent_id = uuid4()
    calls = []

    def fake_service_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "rpc/execution_intent_request_sha256":
            return _Response("a" * 64)
        if path == "rpc/create_execution_intent":
            assert kwargs["json"]["p_request_hash"] == "a" * 64
            return _Response([{"intent_id": str(intent_id), "created": True}])
        raise AssertionError(f"unexpected RPC: {path}")

    monkeypatch.setattr(execution_persistence, "service_request", fake_service_request)
    receipt = execution_persistence.create_execution_intent(
        user_id=user_id,
        idempotency_key="intent-key-0123456789",
        signal_snapshot={"symbol": "BTC/USDT"},
        account_snapshot={"account_ref": "account-1"},
        market_snapshot={"price": 100},
        risk_snapshot={"risk_policy_version": "v1"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert receipt.intent_id == intent_id
    assert receipt.created is True
    assert [call[1] for call in calls] == [
        "rpc/execution_intent_request_sha256",
        "rpc/create_execution_intent",
    ]


def test_intent_creation_rejects_caller_forged_hash(monkeypatch) -> None:
    calls = []

    def fake_service_request(method, path, **kwargs):
        calls.append(path)
        return _Response("a" * 64)

    monkeypatch.setattr(execution_persistence, "service_request", fake_service_request)
    with pytest.raises(DataRequestError, match="does not match canonical"):
        execution_persistence.create_execution_intent(
            user_id=uuid4(),
            idempotency_key="intent-key-0123456789",
            request_hash="b" * 64,
            signal_snapshot={"symbol": "BTC/USDT"},
            account_snapshot={"account_ref": "account-1"},
            market_snapshot={"price": 100},
            risk_snapshot={"risk_policy_version": "v1"},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    assert calls == ["rpc/execution_intent_request_sha256"]


def test_approval_creation_uses_canonical_snapshot_hash(monkeypatch) -> None:
    approval_id = uuid4()
    user_id = uuid4()
    calls = []

    def fake_service_request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path == "rpc/execution_snapshot_sha256":
            return _Response("c" * 64)
        if path == "rpc/record_execution_approval":
            assert kwargs["json"]["p_snapshot_hash"] == "c" * 64
            return _Response(str(approval_id))
        raise AssertionError(f"unexpected RPC: {path}")

    monkeypatch.setattr(execution_persistence, "service_request", fake_service_request)
    receipt = execution_persistence.record_execution_approval(
        user_id=user_id,
        intent_id=uuid4(),
        decision="APPROVE",
        actor_user_id=user_id,
        approval_snapshot={"symbol": "BTC/USDT", "quantity": 1},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert receipt.approval_id == approval_id
    assert [call[1] for call in calls] == [
        "rpc/execution_snapshot_sha256",
        "rpc/record_execution_approval",
    ]


def test_approval_rejects_caller_forged_hash(monkeypatch) -> None:
    calls = []

    def fake_service_request(method, path, **kwargs):
        calls.append(path)
        return _Response("c" * 64)

    monkeypatch.setattr(execution_persistence, "service_request", fake_service_request)
    with pytest.raises(DataRequestError, match="does not match its canonical content"):
        execution_persistence.record_execution_approval(
            user_id=uuid4(),
            intent_id=uuid4(),
            decision="APPROVE",
            actor_user_id=uuid4(),
            approval_snapshot={"symbol": "BTC/USDT", "quantity": 1},
            snapshot_hash="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

    assert calls == ["rpc/execution_snapshot_sha256"]
