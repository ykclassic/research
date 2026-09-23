from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.config import settings


class BillingProviderError(Exception):
    pass


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


class BillingProvider(Protocol):
    name: str
    def create_checkout(self, *, user_id: str, email: str, plan_id: str) -> CheckoutSession: ...
    def get_subscription(self, provider_subscription_id: str) -> dict[str, Any]: ...
    def get_checkout_session(self, checkout_session_id: str) -> dict[str, Any]: ...
    def change_subscription(self, provider_subscription_id: str, *, price_id: str) -> dict[str, Any]: ...
    def cancel_subscription(self, provider_subscription_id: str, *, at_period_end: bool) -> dict[str, Any]: ...
    def resume_subscription(self, provider_subscription_id: str) -> dict[str, Any]: ...
    def verify_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]: ...


class StripeBillingProvider:
    name = "stripe"

    def _request(self, method: str, path: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
        if not settings.stripe_secret_key:
            raise BillingProviderError("Stripe billing is not configured.")
        response = httpx.request(
            method,
            f"https://api.stripe.com/v1/{path}",
            auth=(settings.stripe_secret_key, ""),
            data=data,
            timeout=settings.http_timeout_seconds,
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "Stripe request failed.")
            except ValueError:
                detail = "Stripe request failed."
            raise BillingProviderError(detail)
        return response.json()

    def create_checkout(self, *, user_id: str, email: str, plan_id: str) -> CheckoutSession:
        price_id = {"pro": settings.stripe_price_pro, "premium": settings.stripe_price_premium}.get(plan_id)
        if not price_id:
            raise BillingProviderError(f"No Stripe price is configured for plan '{plan_id}'.")
        payload = self._request(
            "POST",
            "checkout/sessions",
            data={
                "mode": "subscription",
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "success_url": settings.stripe_success_url,
                "cancel_url": settings.stripe_cancel_url,
                "customer_email": email,
                "client_reference_id": user_id,
                "metadata[user_id]": user_id,
                "metadata[plan_id]": plan_id,
                "subscription_data[metadata][user_id]": user_id,
                "subscription_data[metadata][plan_id]": plan_id,
            },
        )
        return CheckoutSession(id=str(payload["id"]), url=str(payload["url"]))

    def get_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        return self._request("GET", f"subscriptions/{provider_subscription_id}")

    def get_checkout_session(self, checkout_session_id: str) -> dict[str, Any]:
        return self._request("GET", f"checkout/sessions/{checkout_session_id}")

    def change_subscription(self, provider_subscription_id: str, *, price_id: str) -> dict[str, Any]:
        subscription = self._request("GET", f"subscriptions/{provider_subscription_id}")
        item = subscription.get("items", {}).get("data", [])
        if not item:
            raise BillingProviderError("Stripe subscription has no billable item.")
        return self._request(
            "POST",
            f"subscriptions/{provider_subscription_id}",
            data={
                "items[0][id]": item[0]["id"],
                "items[0][price]": price_id,
                "proration_behavior": "create_prorations",
            },
        )

    def cancel_subscription(self, provider_subscription_id: str, *, at_period_end: bool) -> dict[str, Any]:
        if at_period_end:
            return self._request(
                "POST",
                f"subscriptions/{provider_subscription_id}",
                data={"cancel_at_period_end": "true"},
            )
        return self._request("DELETE", f"subscriptions/{provider_subscription_id}")

    def resume_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"subscriptions/{provider_subscription_id}",
            data={"cancel_at_period_end": "false"},
        )

    def verify_webhook(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        if not settings.stripe_webhook_secret:
            raise BillingProviderError("Stripe webhook verification is not configured.")
        if not signature:
            raise BillingProviderError("Missing Stripe webhook signature.")
        try:
            parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
            timestamp_value = int(parts["t"])
            provided_values = [item.split("=", 1)[1] for item in signature.split(",") if item.startswith("v1=")]
        except (KeyError, IndexError, ValueError) as exc:
            raise BillingProviderError("Invalid Stripe webhook signature.") from exc
        signed = f"{timestamp_value}.{payload.decode('utf-8')}".encode()
        expected = hmac.new(settings.stripe_webhook_secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, provided) for provided in provided_values):
            raise BillingProviderError("Invalid Stripe webhook signature.")
        return json.loads(payload.decode("utf-8"))


def get_billing_provider() -> BillingProvider:
    if settings.billing_provider == "stripe":
        return StripeBillingProvider()
    raise BillingProviderError(f"Unsupported billing provider: {settings.billing_provider}")
