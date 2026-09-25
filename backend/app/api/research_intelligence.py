from __future__ import annotations

from typing import Annotated

import secrets
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.config import settings
from app.models.research_intelligence import ResearchComparison
from app.services.research_intelligence import (
    catalysts,
    compare,
    create_watchpoint,
    delete_watchpoint,
    evaluate_watchpoints,
    get_snapshot,
    list_snapshots,
    list_watchpoint_events,
    list_watchpoints,
    save_snapshot,
    update_watchpoint,
    run_research_intelligence_cycle,
)

router = APIRouter(prefix="/api/research-intelligence", tags=["research-intelligence"])


class WatchpointRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    condition_type: str = Field(pattern="^(FIELD_THRESHOLD|FIELD_EQUALS|SUPPORT_LOSS|REGIME_CHANGE)$")
    field: str = Field(min_length=1, max_length=120)
    operator: str = Field(pattern="^(eq|gt|gte|lt|lte)$")
    value: object | None = None
    timeframe: str | None = Field(default=None, max_length=12)
    enabled: bool = True


class WatchpointPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    value: object | None = None
    operator: str | None = Field(default=None, pattern="^(eq|gt|gte|lt|lte)$")


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


@router.get("/timeline")
async def timeline(
    user: Annotated[UserResponse, Depends(get_current_user)],
    symbol: str = Query(min_length=1, max_length=32),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    return {"items": list_snapshots(token, user.id, symbol.upper())}


@router.get("/compare", response_model=ResearchComparison)
async def comparison(
    user: Annotated[UserResponse, Depends(get_current_user)],
    symbol: str = Query(min_length=1, max_length=32),
    baseline: str = Query(default="previous_session", pattern="^(previous_session|previous_report|previous_day|previous_week|saved)$"),
    saved_snapshot_id: str | None = Query(default=None),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    snapshots = list_snapshots(token, user.id, symbol.upper())
    if not snapshots:
        raise HTTPException(status_code=404, detail="No research snapshots exist for this asset.")
    current = get_snapshot(token, user.id, snapshots[0].id)
    baseline_snapshot = get_snapshot(token, user.id, saved_snapshot_id) if baseline == "saved" and saved_snapshot_id else None
    if baseline == "saved" and baseline_snapshot is None:
        saved = next((item for item in snapshots if item.snapshot_type == "SAVED"), None)
        baseline_snapshot = get_snapshot(token, user.id, saved.id) if saved else None
    if baseline_snapshot is None:
        from app.services.research_intelligence import _get_baseline
        baseline_snapshot = _get_baseline(snapshots, current, baseline, saved_snapshot_id)
    return compare(current, baseline_snapshot, baseline)


@router.get("/snapshots/{snapshot_id}")
async def snapshot(
    snapshot_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"item": get_snapshot(_token(access_token), user.id, snapshot_id)}


@router.post("/snapshots/{snapshot_id}/save", dependencies=[Depends(_require_csrf)])
async def save_research_snapshot(
    snapshot_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"item": save_snapshot(_token(access_token), user.id, snapshot_id)}


@router.post("/watchpoints", dependencies=[Depends(_require_csrf)])
async def create(
    payload: WatchpointRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"item": create_watchpoint(_token(access_token), user.id, payload.model_dump())}


@router.get("/watchpoints")
async def watchpoints(
    user: Annotated[UserResponse, Depends(get_current_user)],
    symbol: str | None = Query(default=None, max_length=32),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"items": list_watchpoints(_token(access_token), user.id, symbol.upper() if symbol else None)}


@router.patch("/watchpoints/{watchpoint_id}", dependencies=[Depends(_require_csrf)])
async def patch_watchpoint(
    watchpoint_id: str,
    payload: WatchpointPatch,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"item": update_watchpoint(_token(access_token), user.id, watchpoint_id, {k: v for k, v in payload.model_dump().items() if v is not None})}


@router.delete("/watchpoints/{watchpoint_id}", status_code=204, dependencies=[Depends(_require_csrf)])
async def remove_watchpoint(
    watchpoint_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    delete_watchpoint(_token(access_token), user.id, watchpoint_id)


@router.get("/watchpoint-events")
async def watchpoint_events(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    return {"items": list_watchpoint_events(_token(access_token), user.id)}


@router.post("/watchpoints/evaluate/{snapshot_id}", dependencies=[Depends(_require_csrf)])
async def evaluate(
    snapshot_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    token = _token(access_token)
    snapshot = get_snapshot(token, user.id, snapshot_id)
    return {"items": evaluate_watchpoints(token, user.id, snapshot)}


@router.get("/catalysts")
async def catalyst_feed(
    user: Annotated[UserResponse, Depends(get_current_user)],
    symbol: str | None = Query(default=None, max_length=32),
    days: int = Query(default=7, ge=1, le=30),
    limit: int = Query(default=25, ge=1, le=50),
):
    try:
        return {"items": await catalysts(symbol.upper() if symbol else None, days, limit)}
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/scheduler/run")
async def scheduler_run(x_research_scheduler_secret: Annotated[str | None, Header()] = None):
    if not settings.scanner_scheduler_secret or not x_research_scheduler_secret or not secrets.compare_digest(
        x_research_scheduler_secret, settings.scanner_scheduler_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid research intelligence scheduler credential.")
    try:
        return await run_research_intelligence_cycle(settings.supabase_service_role_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Research intelligence scheduler failed.") from exc
