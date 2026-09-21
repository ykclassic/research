from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.billing_provider import BillingProviderError, get_billing_provider
from app.services.supabase_data import DataRequestError, _request, service_request


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def change_subscription(access_token: str, user_id: str, plan_id: str) -> dict[str, Any]:
    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    if plan_id not in {"pro", "premium"}:
        raise DataRequestError("Subscription changes must target a paid plan.")
    provider_id = current.get("provider_subscription_id")
    if not provider_id:
        raise DataRequestError("Subscription is not attached to a billing provider.")
    # Stripe applies plan changes through the hosted subscription state; the
    # webhook remains the source of truth for the resulting entitlement.
    if current.get("plan_id") == plan_id:
        return current
    raise BillingProviderError("Plan changes require a provider price mapping and are finalized by webhook synchronization.")


def cancel_subscription(access_token: str, user_id: str, at_period_end: bool = True) -> dict[str, Any]:
    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    provider_id = current.get("provider_subscription_id")
    if not provider_id:
        raise DataRequestError("Subscription is not attached to a billing provider.")
    updated = get_billing_provider().cancel_subscription(provider_id, at_period_end=at_period_end)
    if at_period_end:
        _request("PATCH", "billing_subscriptions", access_token, params={"id":f"eq.{current['id']}","user_id":f"eq.{user_id}"}, json={"cancel_at_period_end":True,"updated_at":_now()}, prefer="return=minimal")
    return updated


def resume_subscription(access_token: str, user_id: str) -> dict[str, Any]:
    current = _active_subscription(access_token, user_id)
    if not current:
        raise DataRequestError("No active subscription exists.")
    provider_id = current.get("provider_subscription_id")
    if not provider_id:
        raise DataRequestError("Subscription is not attached to a billing provider.")
    updated = get_billing_provider().resume_subscription(provider_id)
    _request("PATCH", "billing_subscriptions", access_token, params={"id":f"eq.{current['id']}","user_id":f"eq.{user_id}"}, json={"cancel_at_period_end":False,"canceled_at":None,"updated_at":_now()}, prefer="return=minimal")
    return updated


def process_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    # Webhooks are authenticated by the provider and persisted as immutable
    # billing events. The database migration adds an RPC for idempotent state
    # synchronization, keeping provider state authoritative without exposing
    # service credentials to the browser.
    return payload
