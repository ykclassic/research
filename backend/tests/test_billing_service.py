from unittest.mock import Mock

from app.services import billing_service


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
        "plan_id": "pro",
        "status": "active",
        "provider": "stripe",
        "provider_subscription_id": "sub_stripe",
    }
    provider = Mock()
    provider.change_subscription.return_value = {"id": "sub_stripe", "status": "active"}

    monkeypatch.setattr(billing_service, "_active_subscription", lambda *_: current)
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)
    monkeypatch.setattr(billing_service.settings, "stripe_price_premium", "price_premium")

    result = billing_service.change_subscription("token", "user", "user@example.com", "premium")

    assert result["status"] == "active"
    assert result["plan_id"] == "premium"
    provider.change_subscription.assert_called_once_with(
        "sub_stripe", price_id="price_premium"
    )
