from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.execution import ExecutionMode, ExecutionRequest, ExecutionResult
from app.services.execution import build_order_request, execute_order

router = APIRouter(prefix="/api/execution", tags=["execution"])


@router.post("/order", response_model=ExecutionResult)
async def submit_execution(request: ExecutionRequest) -> ExecutionResult:
    """Submit a risk-qualified order through the broker boundary.

    The endpoint is paper-safe by default. LIVE requests are rejected until a
    broker adapter that explicitly supports live execution is wired in. Every
    non-research submission also requires explicit human authorization.
    """
    try:
        order = build_order_request(
            request.position,
            request.execution_mode,
            request.client_order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await execute_order(order, request.authorization)
