from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.models.market import Timeframe
from app.models.signal import CryptoSignal
from app.models.signal_outcome import SignalOutcomeAuditRecord, SignalOutcomeStatus
from app.services.signal_outcomes import (
    append_outcome_snapshot,
    create_signal_audit,
    evaluate_first_touch,
    get_signal_audit,
    list_signal_audits,
)
from app.services.supabase_data import (
    DataConflictError,
    DataNotFoundError,
    DataServiceError,
)
from app.services.system_status import APPLICATION_VERSION
from app.providers.kraken_public import KrakenPublicProvider
from app.services.quote_service import QuoteService
from datetime import datetime, timezone

router = APIRouter(prefix="/api/signal-outcomes", tags=["signal-outcomes"])

quote_service = QuoteService()
kraken_public = KrakenPublicProvider()


class LogSignalRequest(BaseModel):
    signal: CryptoSignal


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _map_error(exc: DataServiceError) -> HTTPException:
    if isinstance(exc, DataConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, DataNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(
        status_code=503,
        detail="Signal outcome persistence is temporarily unavailable.",
    )


async def _historical_candles(record: SignalOutcomeAuditRecord):
    start = record.dispatched_at.astimezone(timezone.utc)
    end = datetime.now(timezone.utc)
    mapping = record.symbol

    if record.provider == "kraken_public":
        return await kraken_public.get_candles(
            mapping,
            Timeframe.MINUTE_15,
            5000,
            start_date=start,
            end_date=end,
        )

    return await quote_service.orchestrator.get_candles(
        mapping,
        Timeframe.MINUTE_15,
        5000,
        start_date=start,
        end_date=end,
    )


@router.post(
    "/log",
    response_model=SignalOutcomeAuditRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_csrf)],
)
async def log_signal(
    payload: LogSignalRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return create_signal_audit(
            _token(access_token),
            user.id,
            payload.signal,
            signal_engine_version=APPLICATION_VERSION,
        )
    except (DataServiceError, ValueError) as exc:
        if isinstance(exc, DataServiceError):
            raise _map_error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[SignalOutcomeAuditRecord])
async def outcomes(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    limit: int = Query(50, ge=1, le=100),
):
    try:
        return list_signal_audits(_token(access_token), user.id, limit=limit)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.get("/{signal_id}", response_model=SignalOutcomeAuditRecord)
async def outcome(
    signal_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    refresh: bool = Query(True),
):
    token = _token(access_token)
    try:
        record = get_signal_audit(token, user.id, signal_id)
        if record.outcome != SignalOutcomeStatus.PENDING or not refresh:
            return record

        dataset = await _historical_candles(record)
        result = evaluate_first_touch(record, dataset.completed_candles)
        if result is None:
            return record
        return append_outcome_snapshot(token, user.id, record, result)
    except DataServiceError as exc:
        raise _map_error(exc) from exc
    except (RuntimeError, TimeoutError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to evaluate signal outcome: {exc}",
        ) from exc
