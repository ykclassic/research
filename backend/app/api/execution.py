from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException

from app.api.auth import SESSION_COOKIE, UserResponse, _require_csrf, get_current_user
from app.models.execution import ExecutionRequest, ExecutionResult
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/execution", tags=["execution"])

EXECUTION_FEATURE = "live_trade_execution"


@router.post("/order", response_model=ExecutionResult)
async def submit_execution(
    payload: ExecutionRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    _: Annotated[None, Depends(_require_csrf)],
    access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> ExecutionResult:
    """Fail closed until server-side approval persistence and revalidation exist.

    Client-supplied approval assertions are not accepted as authorization.
    This boundary authenticates the caller, validates CSRF, and checks the
    current server-side entitlement, but intentionally never calls an adapter.
    """
    del payload  # The public request is not actionable until the contract is complete.

    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        require_feature(access_token, user.id, EXECUTION_FEATURE)
    except FeatureNotEntitledError as exc:
        raise HTTPException(
            status_code=403,
            detail="Live execution is not available for this account.",
        ) from exc
    except DataServiceError as exc:
        # Never leak provider/database details. Any entitlement lookup failure
        # must deny the request rather than permit a fallback.
        raise HTTPException(
            status_code=503,
            detail="Execution authorization could not be verified.",
        ) from exc

    # Premium entitlement alone is not sufficient. No persisted approval ledger,
    # snapshot revalidation, idempotency barrier, or live execution gate exists.
    raise HTTPException(
        status_code=503,
        detail="Execution is disabled until server-side approvals and revalidation are implemented.",
    )
