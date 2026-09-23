from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.config import settings
from app.services.entitlement import EntitlementError, get_entitlement_snapshot, get_usage, start_pro_trial
from app.services.billing_provider import BillingProviderError, get_billing_provider
from app.services.billing_service import cancel_subscription, change_subscription, process_webhook, reconcile_checkout_session, resume_subscription, start_checkout
from app.services.supabase_data import DataConflictError, DataRequestError, DataUnavailableError, _request

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlanRequest(BaseModel):
    plan_id: str = Field(min_length=2, max_length=32)


class CheckoutReconcileRequest(BaseModel):
    # Stripe Checkout session IDs are longer than normal plan IDs.
    session_id: str = Field(min_length=2, max_length=255)


class CancelRequest(BaseModel):
    at_period_end: bool = True


class TrialRequest(BaseModel):
    days: int = Field(default=14, ge=1, le=30)


def _token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (EntitlementError, BillingProviderError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=503, detail="Billing service is temporarily unavailable.")


@router.get("/plans")
async def plans(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        rows = _request(
            "GET", "billing_plans", _token(access_token),
            params={"select":"id,name,description,monthly_price_minor,currency,display_order,active", "active":"eq.true", "order":"display_order.asc"},
        ).json()
        return {"plans": rows, "billing_test_mode": bool(settings.billing_test_mode and settings.app_env.lower() != "production")}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/entitlements")
async def entitlements(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return get_entitlement_snapshot(_token(access_token), user.id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/subscription")
async def subscription(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        snapshot = get_entitlement_snapshot(_token(access_token), user.id)
        return {"plan": snapshot["plan"], "subscription": snapshot["subscription"], "plan_id": snapshot["plan_id"]}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/usage")
async def usage(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return get_usage(_token(access_token), user.id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/trial", dependencies=[Depends(_require_csrf)])
async def trial(
    request: TrialRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return {"subscription": start_pro_trial(_token(access_token), user.id, request.days)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/history")
async def billing_history(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        rows = _request(
            "GET", "billing_events", _token(access_token),
            params={"select":"id,provider,event_type,processed_at,created_at,payload", "user_id":f"eq.{user.id}", "order":"created_at.desc", "limit":"100"},
        ).json()
        return {"events": rows}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/checkout", dependencies=[Depends(_require_csrf)])
async def checkout(
    request: PlanRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return start_checkout(_token(access_token), user.id, str(user.email), request.plan_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/change", dependencies=[Depends(_require_csrf)])
async def change(
    request: PlanRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return change_subscription(_token(access_token), user.id, str(user.email), request.plan_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/cancel", dependencies=[Depends(_require_csrf)])
async def cancel(
    request: CancelRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return cancel_subscription(_token(access_token), user.id, request.at_period_end)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/resume", dependencies=[Depends(_require_csrf)])
async def resume(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return resume_subscription(_token(access_token), user.id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/reconcile", dependencies=[Depends(_require_csrf)])
async def reconcile(
    request: CheckoutReconcileRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        return reconcile_checkout_session(user.id, request.session_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict[str, Any]:
    try:
        payload = await request.body()
        event = get_billing_provider().verify_webhook(payload, request.headers.get("Stripe-Signature"))
        return process_webhook(event)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
