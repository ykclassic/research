from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.services.billing_provider import BillingProviderError, get_billing_provider
from app.services.supabase_data import DataRequestError, _request, service_request


LIVE_STATUSES = ("trialing", "active", "past_due", "unpaid", "paused")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stripe_price_id(plan_id: str) -> str:
    price_id = {"pro": settings.stripe_price_pro, "premium": settings.stripe_price_premium}.get(plan_id, "")
    if not price_id:
        raise BillingProviderError(f"No Stripe price is configured for plan '{plan_id}'.")
    return price_id


def _active_subscription(access_token: str, user_id: str) -> dict[str, Any] | None:
    rows = _request(
        "GET", "billing_subscriptions", access_token,
        params={"select":"*","user_id":f"eq.{user_id}","status":"in.(trialing,active,past_due,unpaid,paused)","order":"updated_at.desc","limit":"1"},
    ).json()
    return rows[0] if rows else None


def start_checkout(access_token: str, user_id: str, email: str, plan_id: str) -> dict[str, Any]:
    if plan_id not in {"pro", "premium"}:
        raise BillingProviderError("Only paid plans can be purchased.")
    provider = get_billing_provider()
    session = provider.create_checkout(user_id=user_id, email=email, plan_id=plan_id)
    return {"provider": provider.name, "checkout_session_id": session.id, "checkout_url": session.url, "plan_id": plan_id}


def _test_change_subscription(access_token: str, user_id: str, plan_id: str) -> dict[str, Any]:
    """Instant local billing simulator used only in non-production test environments.

    It exercises the same subscription/entitlement persistence path while never
    contacting Stripe. Real billing remains provider-backed through Stripe.
    """
    if plan_id not in {"free", "pro", "premium"}:
        raise DataRequestError("Unknown test billing plan.")

    current = _active_subscription(access_token, user_id)
    now = _now()

    if plan_id == "free":
        if current:
            rows = service_request(
                "PATCH",
                "billing_subscriptions",
                params={"id": f"eq.{current['id']}", "user_id": f"eq.{user_id}"},
                json={
                    "plan_id": "free",
                    "status": "canceled",
                    "provider": "test",
                    "provider_customer_id": None,
                    "provider_subscription_id": None,
                    "trial_started_at": None,
                    "trial_ends_at": None,
                    "cancel_at_period_end": False,
                    "canceled_at": now,
                    "updated_at": now,
                },
                prefer="return=representation",
            ).json()
            subscription = rows[0] if rows else None
        else:
            subscription = None
    else:
        values = {
            "plan_id": plan_id,
            "status": "active",
            "provider": "test",
            "provider_customer_id": f"test_customer_{user_id}",
            "provider_subscription_id": f"test_subscription_{user_id}",
            "trial_started_at": None,
            "trial_ends_at": None,
            "current_period_start": now,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "canceled_at": None,
            "updated_at": now,
        }
        if current:
            rows = service_request(
                "PATCH",
                "billing_subscriptions",
                params={"id": f"eq.{current['id']}", "user_id": f"eq.{user_id}"},
                json=values,
                prefer="return=representation",
            ).json()
        else:
            values["user_id"] = user_id
            rows = service_request(
                "POST",
                "billing_subscriptions",
                json=values,
                prefer="return=representation",
            ).json()
        subscription = rows[0] if rows else None

    service_request(
        "POST",
        "billing_events",
        json={
            "provider": "test",
            "provider_event_id": f"test-{user_id}-{now}",
            "user_id": user_id,
            "event_type": "test.subscription.changed",
            "payload": {"plan_id": plan_id, "subscription_id": subscription.get("id") if subscription else None},
            "processed_at": now,
        },
        prefer="return=minimal",
    )
    return {"status": "test_updated", "plan_id": plan_id, "subscription": subscription}


def change_subscription(access_token: str, user_id: str, email: str, plan_id: str) -> dict[str, Any]:
    if settings.billing_test_mode and settings.app_env.lower() != "production":
        return _test_change_subscription(access_token, user_id, plan_id)

    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    if plan_id not in {"pro", "premium"}:
        raise DataRequestError("Subscription changes must target a paid plan.")
    if current.get("plan_id") == plan_id:
        return {"status": current.get("status", "active"), "plan_id": plan_id, "subscription": current}

    provider = get_billing_provider()
    provider_id = current.get("provider_subscription_id")

    # A Pro trial is an internal entitlement with no Stripe subscription yet.
    # Start hosted checkout and let the signed Stripe subscription webhook
    # replace the trial row with the provider-backed subscription. Keeping the
    # trial row until checkout completes avoids losing the trial on abandonment.
    if not provider_id:
        if current.get("provider") == "internal" and current.get("status") == "trialing":
            session = provider.create_checkout(user_id=user_id, email=email, plan_id=plan_id)
            return {
                "status": "checkout_required",
                "plan_id": plan_id,
                "checkout_session_id": session.id,
                "checkout_url": session.url,
            }
        raise BillingProviderError("Current subscription is not connected to the billing provider.")

    updated = provider.change_subscription(provider_id, price_id=_stripe_price_id(plan_id))
    subscription_metadata = updated.setdefault("metadata", {})
    subscription_metadata["user_id"] = str(user_id)
    # The Stripe subscription may retain metadata from the previous plan.
    # The requested price change is authoritative for this interactive update.
    subscription_metadata["plan_id"] = plan_id
    synced = _sync_subscription(updated)
    if not synced:
        raise DataRequestError("Stripe subscription could not be synchronized after the plan change.")
    return {
        "status": str(synced.get("status", updated.get("status", "updated"))),
        "plan_id": synced.get("plan_id", plan_id),
        "subscription": synced,
    }


def cancel_subscription(access_token: str, user_id: str, at_period_end: bool = True) -> dict[str, Any]:
    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    provider_id = current.get("provider_subscription_id")
    if not provider_id:
        raise DataRequestError("Subscription is not attached to a billing provider.")
    updated = get_billing_provider().cancel_subscription(provider_id, at_period_end=at_period_end)
    if at_period_end:
        service_request("PATCH", "billing_subscriptions", params={"id":f"eq.{current['id']}","user_id":f"eq.{user_id}"}, json={"cancel_at_period_end":True,"updated_at":_now()}, prefer="return=minimal")
    return updated


def resume_subscription(access_token: str, user_id: str) -> dict[str, Any]:
    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    provider_id = current.get("provider_subscription_id")
    if not provider_id:
        raise DataRequestError("Subscription is not attached to a billing provider.")
    updated = get_billing_provider().resume_subscription(provider_id)
    service_request("PATCH", "billing_subscriptions", params={"id":f"eq.{current['id']}","user_id":f"eq.{user_id}"}, json={"cancel_at_period_end":False,"canceled_at":None,"updated_at":_now()}, prefer="return=minimal")
    return updated


def _epoch_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _subscription_plan(subscription: dict[str, Any]) -> str | None:
    metadata = subscription.get("metadata") or {}
    plan_id = metadata.get("plan_id")
    if plan_id in {"pro", "premium"}:
        return plan_id
    items = ((subscription.get("items") or {}).get("data") or [])
    price = (items[0].get("price") or {}) if items else {}
    price_id = price.get("id")
    if price_id and price_id == settings.stripe_price_pro:
        return "pro"
    if price_id and price_id == settings.stripe_price_premium:
        return "premium"
    return None


def _subscription_user_id(subscription: dict[str, Any]) -> str | None:
    metadata = subscription.get("metadata") or {}
    user_id = metadata.get("user_id")
    return str(user_id) if user_id else None


def _service_live_subscription(user_id: str) -> dict[str, Any] | None:
    rows = service_request(
        "GET", "billing_subscriptions",
        params={"select":"*","user_id":f"eq.{user_id}","status":"in.(trialing,active,past_due,unpaid,paused)","order":"updated_at.desc","limit":"1"},
    ).json()
    return rows[0] if rows else None


def _sync_subscription(subscription: dict[str, Any]) -> dict[str, Any] | None:
    user_id = _subscription_user_id(subscription)
    plan_id = _subscription_plan(subscription)
    provider_subscription_id = subscription.get("id")
    provider_customer_id = subscription.get("customer")
    stripe_status = subscription.get("status")
    if not user_id or not provider_subscription_id:
        return None
    if stripe_status not in {"trialing", "active", "past_due", "unpaid", "paused", "canceled"}:
        return None
    if not plan_id and stripe_status != "canceled":
        return None

    values: dict[str, Any] = {
        "provider": "stripe",
        "provider_customer_id": provider_customer_id,
        "provider_subscription_id": provider_subscription_id,
        "current_period_start": _epoch_iso(subscription.get("current_period_start")),
        "current_period_end": _epoch_iso(subscription.get("current_period_end")),
        "cancel_at_period_end": bool(subscription.get("cancel_at_period_end", False)),
        "canceled_at": _epoch_iso(subscription.get("canceled_at")),
        "updated_at": _now(),
    }
    if stripe_status == "canceled":
        values["status"] = "canceled"
        if plan_id:
            values["plan_id"] = plan_id
    else:
        values["status"] = stripe_status
        values["plan_id"] = plan_id

    current = _service_live_subscription(user_id)
    if current:
        rows = service_request(
            "PATCH", "billing_subscriptions",
            params={"id":f"eq.{current['id']}"},
            json=values,
            prefer="return=representation",
        ).json()
    else:
        values["user_id"] = user_id
        if "plan_id" not in values:
            return None
        rows = service_request(
            "POST", "billing_subscriptions",
            json=values,
            prefer="return=representation",
        ).json()
    return rows[0] if rows else None


def _record_event(event: dict[str, Any], user_id: str | None) -> None:
    event_id = str(event.get("id") or "")
    if not event_id:
        raise BillingProviderError("Stripe webhook event id is missing.")
    existing = service_request(
        "GET", "billing_events",
        params={"select":"id","provider":"eq.stripe","provider_event_id":f"eq.{event_id}","limit":"1"},
    ).json()
    if existing:
        return
    try:
        service_request(
            "POST", "billing_events",
            json={
                "provider": "stripe",
                "provider_event_id": event_id,
                "user_id": user_id,
                "event_type": str(event.get("type") or "unknown"),
                "payload": event,
                "processed_at": _now(),
            },
            prefer="return=minimal",
        )
    except DataRequestError:
        # A concurrent delivery may have inserted the same unique event.
        pass


def reconcile_checkout_session(user_id: str, checkout_session_id: str) -> dict[str, Any]:
    """Reconcile a completed Checkout session directly with Stripe."""
    if not checkout_session_id or len(checkout_session_id) > 255:
        raise DataRequestError("Invalid Checkout session.")
    provider = get_billing_provider()
    session = provider.get_checkout_session(checkout_session_id)
    metadata = session.get("metadata") or {}
    session_user_id = str(metadata.get("user_id") or session.get("client_reference_id") or "")
    if session_user_id != str(user_id):
        raise DataRequestError("Checkout session does not belong to the signed-in user.")
    if session.get("mode") != "subscription" or session.get("status") != "complete":
        raise DataRequestError("Checkout session is not complete.")
    subscription_id = session.get("subscription")
    if not subscription_id:
        raise DataRequestError("Checkout session has no subscription.")
    subscription = provider.get_subscription(str(subscription_id))
    subscription_metadata = subscription.setdefault("metadata", {})
    subscription_metadata.setdefault("user_id", str(user_id))
    subscription_metadata.setdefault("plan_id", metadata.get("plan_id"))
    synced = _sync_subscription(subscription)
    if not synced:
        raise DataRequestError("Stripe subscription could not be synchronized.")
    _record_event({"id": f"checkout-reconcile-{checkout_session_id}", "type": "checkout.session.reconciled", "data": {"object": session}}, str(user_id))
    return {"status": "synchronized", "plan_id": synced.get("plan_id"), "subscription": synced}


def process_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("type") or "")
    obj = ((payload.get("data") or {}).get("object") or {})
    user_id: str | None = None

    if event_type == "checkout.session.completed":
        metadata = obj.get("metadata") or {}
        user_id = str(metadata.get("user_id")) if metadata.get("user_id") else None
        subscription_id = obj.get("subscription")
        customer_id = obj.get("customer")
        if user_id and subscription_id:
            current = _service_live_subscription(user_id)
            if current:
                service_request(
                    "PATCH", "billing_subscriptions",
                    params={"id":f"eq.{current['id']}"},
                    json={
                        "provider": "stripe",
                        "provider_customer_id": customer_id,
                        "provider_subscription_id": subscription_id,
                        "updated_at": _now(),
                    },
                    prefer="return=minimal",
                )
            provider = get_billing_provider()
            stripe_subscription = provider.get_subscription(subscription_id)
            metadata = stripe_subscription.setdefault("metadata", {})
            metadata.setdefault("user_id", user_id)
            metadata.setdefault("plan_id", metadata.get("plan_id") or (obj.get("metadata") or {}).get("plan_id"))
            _sync_subscription(stripe_subscription)
    elif event_type.startswith("customer.subscription."):
        user_id = _subscription_user_id(obj)
        _sync_subscription(obj)

    _record_event(payload, user_id)
    return {"status": "processed", "event_type": event_type}
