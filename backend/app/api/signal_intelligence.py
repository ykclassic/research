from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query

from app.api.auth import UserResponse, get_current_user
from app.services.entitlement import EntitlementError, FeatureNotEntitledError, UsageLimitExceededError
from app.services.signal_intelligence import calibration, engine_version_analytics, explorer, replay, similarity
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/signal-intelligence", tags=["signal-intelligence"])


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _call(fn, token: str, user_id: str, *args, **kwargs):
    try:
        return fn(token, user_id, *args, **kwargs)
    except FeatureNotEntitledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except UsageLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except DataServiceError as exc:
        raise HTTPException(status_code=503, detail="Signal intelligence is temporarily unavailable.") from exc
    except EntitlementError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/explorer")
async def historical_explorer(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    regime: str | None = None,
    strategy: str | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    max_confidence: float | None = Query(None, ge=0, le=1),
    min_rr: float | None = Query(None, ge=0),
    session: str | None = None,
    outcome: str | None = None,
    engine_version: str | None = None,
    structure: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
):
    filters = locals()
    filters.pop("user", None); filters.pop("access_token", None)
    return _call(explorer, _token(access_token), user.id, filters)


@router.get("/calibration")
async def confidence_calibration(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return _call(calibration, _token(access_token), user.id)


@router.get("/engine-versions")
async def engine_versions(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return _call(engine_version_analytics, _token(access_token), user.id)


@router.get("/similar/{signal_id}")
async def historical_similarity(
    signal_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return _call(similarity, _token(access_token), user.id, signal_id)


@router.get("/replay/{signal_id}")
async def signal_replay(
    signal_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return _call(replay, _token(access_token), user.id, signal_id)
