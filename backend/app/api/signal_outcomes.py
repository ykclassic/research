from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.signal import CryptoSignal
from app.models.signal_outcome import SignalOutcomeRecord
from app.services.signal_outcomes import (
    append_terminal_outcome, create_signal_audit, evaluate_first_touch,
    get_signal_audit, list_signal_audits,
)
from app.services.system_status import APPLICATION_VERSION
from app.services.supabase_data import DataServiceError
from app.models.market import Timeframe
from app.api.signals import signal_candle_scheduler

router = APIRouter(prefix="/api/signal-outcomes", tags=["signal-outcomes"])


class LogSignalRequest(BaseModel):
    signal: CryptoSignal
    dispatched_at: datetime | None = None


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _map_error(exc: DataServiceError) -> HTTPException:
    if exc.__class__.__name__ == "DataConflictError":
        return HTTPException(status_code=409, detail="This signal could not be logged because the audit record already exists.")
    if exc.__class__.__name__ == "DataNotFoundError":
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=503, detail="Signal outcome persistence is temporarily unavailable.")


@router.post("/log", response_model=SignalOutcomeRecord, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def log_signal(payload: LogSignalRequest, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return create_signal_audit(_token(access_token), user.id, payload.signal, signal_engine_version=APPLICATION_VERSION, dispatched_at=payload.dispatched_at)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.get("", response_model=list[SignalOutcomeRecord])
async def outcomes(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None, limit: int = Query(50, ge=1, le=100)):
    try:
        return list_signal_audits(_token(access_token), user.id, limit=limit)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.get("/{signal_id}", response_model=SignalOutcomeRecord)
async def outcome(signal_id: str, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None, refresh: bool = Query(True)):
    token = _token(access_token)
    try:
        record = get_signal_audit(token, user.id, signal_id)
        if record.outcome != "PENDING" or not refresh:
            return record
        dataset = await signal_candle_scheduler.get_dataset(record.symbol, Timeframe.MINUTE_15, 5000)
        result = evaluate_first_touch(record, dataset.completed_candles)
        if result is None:
            return record
        return append_terminal_outcome(token, user.id, record, result)
    except DataServiceError as exc:
        raise _map_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=f"Unable to evaluate signal outcome: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Unable to evaluate signal outcome: {exc}") from exc
