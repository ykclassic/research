from unittest.mock import Mock

from app.services import billing_service
from app.services.billing_provider import StripeBillingProvider


def test_change_subscription_from_internal_trial_starts_checkout(monkeypatch):
    current = {
        "id": "sub-row",
        "plan_id": "pro",
        "status": "trialing",
        "provider": "internal",
        "provider_subscription_id": None,
    }
    session = Mock(id="cs_trial_upgrade", url="https://checkout.stripe.com/cs_trial_upgrade")
    provider = Mock()
    provider.create_checkout.return_value = session

    monkeypatch.setattr(billing_service, "_active_subscription", lambda *_: current)
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)

    result = billing_service.change_subscription("token", "user", "user@example.com", "premium")

    assert result["status"] == "checkout_required"
    assert result["plan_id"] == "premium"
    assert result["checkout_url"] == session.url
    provider.create_checkout.assert_called_once_with(
        user_id="user", email="user@example.com", plan_id="premium"
    )


def test_change_subscription_updates_stripe_subscription(monkeypatch):
    current = {
        "id": "sub-row",
        "plan_id": "premium",
        "status": "active",
        "provider": "stripe",
        "provider_subscription_id": "sub_stripe",
    }
    provider = Mock()
    provider.change_subscription.return_value = {"id": "sub_stripe", "status": "active", "metadata": {"plan_id": "premium"}}

    synced = {
        "id": "sub-row",
        "plan_id": "pro",
        "status": "active",
        "provider": "stripe",
    }
    sync = Mock(return_value=synced)
    monkeypatch.setattr(billing_service, "_active_subscription", lambda *_: current)
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)
    monkeypatch.setattr(billing_service.settings, "stripe_price_pro", "price_pro")
    monkeypatch.setattr(billing_service, "_sync_subscription", sync)

    result = billing_service.change_subscription("token", "user", "user@example.com", "pro")

    assert result["status"] == "active"
    assert result["plan_id"] == "pro"
    assert result["subscription"] == synced
    provider.change_subscription.assert_called_once_with(
        "sub_stripe", price_id="price_pro"
    )
    sync.assert_called_once_with({
        "id": "sub_stripe",
        "status": "active",
        "metadata": {"user_id": "user", "plan_id": "pro"},
    })


def test_stripe_checkout_carries_identity_into_subscription_metadata(monkeypatch):
    provider = StripeBillingProvider()
    response = {"id": "cs_test", "url": "https://checkout.stripe.com/cs_test"}
    request = Mock(return_value=response)
    monkeypatch.setattr(provider, "_request", request)
    monkeypatch.setattr(billing_service.settings, "stripe_price_premium", "price_premium")

    result = provider.create_checkout(
        user_id="user-123", email="user@example.com", plan_id="premium"
    )

    assert result.id == "cs_test"
    payload = request.call_args.kwargs["data"]
    assert payload["metadata[user_id]"] == "user-123"
    assert payload["metadata[plan_id]"] == "premium"
    assert payload["subscription_data[metadata][user_id]"] == "user-123"
    assert payload["subscription_data[metadata][plan_id]"] == "premium"


def test_checkout_session_completed_syncs_authoritative_subscription(monkeypatch):
    subscription = {
        "id": "sub_premium",
        "customer": "cus_test",
        "status": "active",
        "metadata": {"user_id": "user-123", "plan_id": "premium"},
        "current_period_start": 1770000000,
        "current_period_end": 1772678400,
        "cancel_at_period_end": False,
    }
    provider = Mock()
    provider.get_subscription.return_value = subscription
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)
    monkeypatch.setattr(billing_service, "_service_live_subscription", lambda *_: {"id": "sub-row"})
    patch = Mock(return_value=Mock(json=lambda: [{"id": "sub-row"}]))
    record = Mock()
    monkeypatch.setattr(billing_service, "service_request", patch)
    monkeypatch.setattr(billing_service, "_record_event", record)

    result = billing_service.process_webhook({
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"user_id": "user-123", "plan_id": "premium"},
            "subscription": "sub_premium",
            "customer": "cus_test",
        }},
    })

    assert result["status"] == "processed"
    provider.get_subscription.assert_called_once_with("sub_premium")
    assert any(
        call.kwargs.get("json", {}).get("plan_id") == "premium"
        and call.kwargs.get("json", {}).get("provider_subscription_id") == "sub_premium"
        for call in patch.call_args_list
    )
    record.assert_called_once()
