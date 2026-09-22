from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.services import billing_service


def _response(payload):
    return SimpleNamespace(json=lambda: payload)


def test_test_billing_switches_existing_subscription():
    current = {
        "id": "sub-1",
        "user_id": "user-1",
        "plan_id": "pro",
        "status": "active",
        "provider": "test",
    }
    updated = {**current, "plan_id": "premium", "status": "active", "provider": "test"}

    request = Mock(side_effect=[
        _response([updated]),
        _response([]),
    ])

    with patch.object(billing_service, "_active_subscription", return_value=current),          patch.object(billing_service, "service_request", request):
        result = billing_service._test_change_subscription("token", "user-1", "premium")

    assert result["status"] == "test_updated"
    assert result["plan_id"] == "premium"
    assert result["subscription"]["plan_id"] == "premium"
    assert request.call_args_list[0].args[:2] == ("PATCH", "billing_subscriptions")
    assert request.call_args_list[1].args[:2] == ("POST", "billing_events")


def test_test_billing_switches_back_to_free_without_stripe():
    current = {
        "id": "sub-1",
        "user_id": "user-1",
        "plan_id": "premium",
        "status": "active",
        "provider": "test",
    }
    updated = {**current, "plan_id": "free", "status": "canceled", "provider": "test"}

    request = Mock(side_effect=[
        _response([updated]),
        _response([]),
    ])

    with patch.object(billing_service, "_active_subscription", return_value=current),          patch.object(billing_service, "service_request", request):
        result = billing_service._test_change_subscription("token", "user-1", "free")

    assert result["plan_id"] == "free"
    assert result["subscription"]["status"] == "canceled"
    patch_payload = request.call_args_list[0].kwargs["json"]
    assert patch_payload["provider"] == "test"
    assert patch_payload["provider_subscription_id"] is None
