from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException

from app.api.auth import SESSION_COOKIE, UserResponse, _require_csrf, get_current_user
from app.models.execution import ExecutionApprovalDecisionRequest, ExecutionRequest, ExecutionResult
from app.services.entitlement import FeatureNotEntitledError, require_feature
from app.services.execution_persistence import (
    get_execution_intent_approval_preview,
    record_execution_approval,
)
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
        entitlement = require_feature(access_token, user.id, EXECUTION_FEATURE)
        if entitlement.get("plan_id") != "premium":
            raise HTTPException(
                status_code=403,
                detail="Live execution is available only on the Premium plan.",
            )
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


@router.get("/intents/{intent_id}/approval-preview")
async def get_approval_preview(
    intent_id: UUID,
    user: Annotated[UserResponse, Depends(get_current_user)],
) -> dict:
    """Return exact stored proposal fields for the authenticated owner to review."""
    try:
        return get_execution_intent_approval_preview(
            user_id=UUID(user.id),
            intent_id=intent_id,
        )
    except DataServiceError as exc:
        # Includes foreign, expired, missing, and already-decided intents.
        raise HTTPException(
            status_code=404,
            detail="Execution intent is unavailable for approval.",
        ) from exc


@router.post("/intents/{intent_id}/approval")
async def decide_execution_approval(
    intent_id: UUID,
    payload: ExecutionApprovalDecisionRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    _: Annotated[None, Depends(_require_csrf)],
) -> dict[str, str]:
    """Persist a CSRF-protected decision bound to the currently stored intent.

    The actor is always derived from the verified session. The caller cannot
    submit an actor UUID or an approval snapshot. Execution remains disabled.
    """
    user_id = UUID(user.id)
    try:
        preview = get_execution_intent_approval_preview(
            user_id=user_id,
            intent_id=intent_id,
        )
        if preview["request_hash"] != payload.request_hash:
            raise HTTPException(
                status_code=409,
                detail="The proposal changed. Reload the approval preview before deciding.",
            )

        approval_snapshot = {
            "intent_id": str(intent_id),
            "request_hash": preview["request_hash"],
            "account_ref": preview["account_ref"],
            "symbol": preview["symbol"],
            "side": preview["side"],
            "quantity": preview["quantity"],
            "entry_price": preview["entry_price"],
            "stop_loss": preview["stop_loss"],
            "take_profit": preview["take_profit"],
            "risk_policy_version": preview["risk_policy_version"],
            # This field is a server-generated binding field, not proof of
            # identity. Identity is established by get_current_user above.
            "human_confirmed": True,
        }
        expiry_value = str(preview["expires_at"])
        intent_expires_at = datetime.fromisoformat(
            expiry_value.replace("Z", "+00:00")
        )
        receipt = record_execution_approval(
            user_id=user_id,
            intent_id=intent_id,
            decision=payload.decision,
            actor_user_id=user_id,
            approval_snapshot=approval_snapshot,
            expires_at=intent_expires_at,
        )
        return {"approval_id": str(receipt.approval_id), "decision": payload.decision}
    except HTTPException:
        raise
    except DataServiceError as exc:
        raise HTTPException(
            status_code=409,
            detail="The intent could not be approved; it may be expired or already decided.",
        ) from exc
