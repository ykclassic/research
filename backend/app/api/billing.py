from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.services.entitlement import (
    EntitlementError,
    get_entitlement_snapshot,
    get_usage,
    start_pro_trial,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])


class TrialRequest(BaseModel):
    days: int = Field(default=14, ge=1, le=30)


def _access_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EntitlementError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=503, detail="Billing service is temporarily unavailable.")


@router.get("/plans")
async def plans(user: Annotated[UserResponse, Depends(get_current_user)]) -> dict[str, Any]:
    # Use the user's token so RLS remains the final database boundary.
    from app.services.supabase_data import _request
    token = _access_token_from_dependency(user)
    rows = _request("GET", "billing_plans", token, params={"select":"id,name,description,monthly_price_minor,currency,display_order,active", "active":"eq.true", "order":"display_order.asc"}).json()
    return {"plans": rows}


def _access_token_from_dependency(user: UserResponse) -> str:
    # This function is intentionally not used for authentication; the routes below
    # obtain the raw session cookie because the existing auth architecture keeps it
    # server-side and HttpOnly.
    raise RuntimeError("Use the authenticated route dependency with the session token.")


@router.get("/entitlements")
async def entitlements(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return get_entitlement_snapshot(_access_token(access_token), user.id)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise _map_error(exc) from exc


@router.get("/subscription")
async def subscription(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        snapshot = get_entitlement_snapshot(_access_token(access_token), user.id)
        return {"plan": snapshot["plan"], "subscription": snapshot["subscription"], "plan_id": snapshot["plan_id"]}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/usage")
async def usage(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return get_usage(_access_token(access_token), user.id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/trial", dependencies=[Depends(_require_csrf)])
async def trial(
    request: TrialRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    try:
        return {"subscription": start_pro_trial(_access_token(access_token), user.id, request.days)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/history")
async def billing_history(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> dict[str, Any]:
    from app.services.supabase_data import _request
    try:
        rows = _request(
            "GET", "billing_events", _access_token(access_token),
            params={"select":"id,provider,event_type,processed_at,created_at,payload", "user_id":f"eq.{user.id}", "order":"created_at.desc", "limit":"100"},
        ).json()
        return {"events": rows}
    except Exception as exc:
        raise _map_error(exc) from exc
