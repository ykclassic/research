from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, status

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.config import settings
from app.models.scanner import (
    ScannerPresetCreate,
    ScannerPresetPatch,
    ScannerScheduleCreate,
    ScannerSchedulePatch,
)
from app.services.scanner import (
    create_preset,
    create_schedule,
    delete_preset,
    delete_schedule,
    get_preset,
    latest_opportunities,
    list_presets,
    list_schedules,
    run_due_schedules,
    run_scan,
    update_preset,
    update_schedule,
)
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DataServiceError):
        name = exc.__class__.__name__
        if name == "DataNotFoundError":
            return HTTPException(status_code=404, detail=str(exc))
        return HTTPException(status_code=503, detail=str(exc))
    if exc.__class__.__name__ in {"FeatureNotEntitledError", "UsageLimitExceededError"}:
        return HTTPException(status_code=402, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=503, detail="Scanner operation is temporarily unavailable.")


@router.get("/presets")
async def get_presets(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"items": list_presets(_token(access_token), user.id)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/presets", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def post_preset(payload: ScannerPresetCreate, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"item": create_preset(_token(access_token), user.id, payload)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/presets/{preset_id}", dependencies=[Depends(_require_csrf)])
async def patch_preset(preset_id: str, payload: ScannerPresetPatch, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"item": update_preset(_token(access_token), user.id, preset_id, payload)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove_preset(preset_id: str, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        delete_preset(_token(access_token), user.id, preset_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/presets/{preset_id}/scan", dependencies=[Depends(_require_csrf)])
async def scan_preset(preset_id: str, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return await run_scan(_token(access_token), user.id, preset_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/opportunities")
async def get_opportunities(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"items": latest_opportunities(_token(access_token), user.id)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/schedules")
async def get_schedules(user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"items": list_schedules(_token(access_token), user.id)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/schedules", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def post_schedule(payload: ScannerScheduleCreate, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"item": create_schedule(_token(access_token), user.id, payload)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/schedules/{schedule_id}", dependencies=[Depends(_require_csrf)])
async def patch_schedule(schedule_id: str, payload: ScannerSchedulePatch, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        return {"item": update_schedule(_token(access_token), user.id, schedule_id, payload)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove_schedule(schedule_id: str, user: Annotated[UserResponse, Depends(get_current_user)], access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None):
    try:
        delete_schedule(_token(access_token), user.id, schedule_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/scheduler/run", dependencies=[Depends(_require_csrf)])
async def scheduler_run(x_scanner_scheduler_secret: Annotated[str | None, Header()] = None):
    if not settings.scanner_scheduler_secret or not x_scanner_scheduler_secret or not secrets.compare_digest(x_scanner_scheduler_secret, settings.scanner_scheduler_secret):
        raise HTTPException(status_code=401, detail="Invalid scanner scheduler credential.")
    return await run_due_schedules()
