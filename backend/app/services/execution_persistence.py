from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Literal
from uuid import UUID

from app.services.supabase_data import DataRequestError, service_request


ApprovalDecision = Literal["APPROVE", "REJECT"]
ExecutionResultStatus = Literal["FILLED", "FAILED", "REJECTED", "UNKNOWN"]


@dataclass(frozen=True)
class IntentReceipt:
    intent_id: UUID
    created: bool


@dataclass(frozen=True)
class ExecutionApprovalReceipt:
    approval_id: UUID


@dataclass(frozen=True)
class ExecutionRecordReceipt:
    execution_record_id: UUID


def _rpc(name: str, payload: dict[str, Any]) -> Any:
    """Invoke a transactional execution persistence RPC using server credentials.

    Callers must authenticate the user and enforce entitlement before invoking
    these functions. This module deliberately has no exchange adapter and never
    submits orders.
    """
    response = service_request("POST", f"rpc/{name}", json=payload)
    try:
        return response.json()
    except ValueError as exc:
        raise DataRequestError("Execution persistence returned an invalid response.") from exc


def create_execution_intent(
    *,
    user_id: UUID,
    idempotency_key: str,
    request_hash: str | None = None,
    signal_snapshot: dict[str, Any],
    account_snapshot: dict[str, Any],
    market_snapshot: dict[str, Any],
    risk_snapshot: dict[str, Any],
    expires_at: datetime,
) -> IntentReceipt:
    canonical_request_hash = _rpc(
        "execution_intent_request_sha256",
        {
            "p_signal_snapshot": signal_snapshot,
            "p_account_snapshot": account_snapshot,
            "p_market_snapshot": market_snapshot,
            "p_risk_snapshot": risk_snapshot,
        },
    )
    if not isinstance(canonical_request_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", canonical_request_hash):
        raise DataRequestError("Canonical execution request hash could not be verified.")
    if request_hash is not None and request_hash != canonical_request_hash:
        raise DataRequestError("Request hash does not match canonical execution snapshots.")

    rows = _rpc(
        "create_execution_intent",
        {
            "p_user_id": str(user_id),
            "p_idempotency_key": idempotency_key,
            "p_request_hash": canonical_request_hash,
            "p_signal_snapshot": signal_snapshot,
            "p_account_snapshot": account_snapshot,
            "p_market_snapshot": market_snapshot,
            "p_risk_snapshot": risk_snapshot,
            "p_expires_at": expires_at.isoformat(),
        },
    )
    if not isinstance(rows, list) or not rows or not rows[0].get("intent_id"):
        raise DataRequestError("Execution intent was not persisted.")
    row = rows[0]
    return IntentReceipt(intent_id=UUID(row["intent_id"]), created=bool(row["created"]))


def record_execution_approval(
    *,
    user_id: UUID,
    intent_id: UUID,
    decision: ApprovalDecision,
    actor_user_id: UUID,
    approval_snapshot: dict[str, Any],
    snapshot_hash: str | None = None,
    expires_at: datetime,
) -> ExecutionApprovalReceipt:
    canonical_snapshot_hash = _rpc(
        "execution_snapshot_sha256",
        {"p_snapshot": approval_snapshot},
    )
    if not isinstance(canonical_snapshot_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", canonical_snapshot_hash):
        raise DataRequestError("Canonical approval snapshot hash could not be verified.")
    if snapshot_hash is not None and snapshot_hash != canonical_snapshot_hash:
        raise DataRequestError("Approval snapshot hash does not match its canonical content.")

    approval_id = _rpc(
        "record_execution_approval",
        {
            "p_user_id": str(user_id),
            "p_intent_id": str(intent_id),
            "p_decision": decision,
            "p_actor_user_id": str(actor_user_id),
            "p_approval_snapshot": approval_snapshot,
            "p_snapshot_hash": canonical_snapshot_hash,
            "p_expires_at": expires_at.isoformat(),
        },
    )
    if not isinstance(approval_id, str):
        raise DataRequestError("Execution approval was not persisted.")
    return ExecutionApprovalReceipt(approval_id=UUID(approval_id))


def claim_execution(
    *,
    user_id: UUID,
    intent_id: UUID,
    approval_id: UUID,
    revalidation_snapshot: dict[str, Any],
    revalidation_hash: str,
) -> None:
    claimed = _rpc(
        "claim_execution",
        {
            "p_user_id": str(user_id),
            "p_intent_id": str(intent_id),
            "p_approval_id": str(approval_id),
            "p_revalidation_snapshot": revalidation_snapshot,
            "p_revalidation_hash": revalidation_hash,
        },
    )
    if claimed is not True:
        raise DataRequestError("Execution claim could not be confirmed.")


def record_execution_result(
    *,
    user_id: UUID,
    intent_id: UUID,
    approval_id: UUID,
    idempotency_key: str,
    result_status: ExecutionResultStatus,
    broker_order_id: str | None,
    result_snapshot: dict[str, Any],
) -> ExecutionRecordReceipt:
    record_id = _rpc(
        "record_execution_result",
        {
            "p_user_id": str(user_id),
            "p_intent_id": str(intent_id),
            "p_approval_id": str(approval_id),
            "p_idempotency_key": idempotency_key,
            "p_result_status": result_status,
            "p_broker_order_id": broker_order_id,
            "p_result_snapshot": result_snapshot,
        },
    )
    if not isinstance(record_id, str):
        raise DataRequestError("Execution result was not persisted.")
    return ExecutionRecordReceipt(execution_record_id=UUID(record_id))


def get_execution_intent_approval_preview(*, user_id: UUID, intent_id: UUID) -> dict[str, Any]:
    """Load the immutable, owner-scoped proposal fields for explicit approval.

    The database RPC enforces ownership and only returns intents that are still
    awaiting approval and unexpired. Callers must derive user_id from a verified
    authenticated session; never accept it from request JSON.
    """
    preview = _rpc(
        "get_execution_intent_approval_preview",
        {"p_user_id": str(user_id), "p_intent_id": str(intent_id)},
    )
    if not isinstance(preview, dict):
        raise DataRequestError("Execution intent preview could not be verified.")
    required = {
        "intent_id", "request_hash", "account_ref", "symbol", "side", "quantity",
        "entry_price", "stop_loss", "take_profit", "risk_policy_version", "expires_at",
    }
    if not required.issubset(preview) or not re.fullmatch(
        r"[a-f0-9]{64}", str(preview.get("request_hash", ""))
    ):
        raise DataRequestError("Execution intent preview is incomplete.")
    return preview
