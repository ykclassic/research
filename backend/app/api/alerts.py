from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.services.alerts import (
    create_rule,
    delete_rule,
    evaluate_rules,
    get_rule,
    list_events,
    list_rules,
    mark_event_read,
    set_rule_enabled,
    update_rule,
)
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertRuleRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    condition_type: str
    operator: str | None = None
    threshold: float | None = None
    timeframe: str = "1h"
    enabled: bool = True
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)
    channels: list[str] = Field(default_factory=lambda: ["WEB"])


class AlertRulePatch(BaseModel):
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    condition_type: str | None = None
    operator: str | None = None
    threshold: float | None = None
    timeframe: str | None = None
    enabled: bool | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)
    channels: list[str] | None = None


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DataServiceError):
        name = exc.__class__.__name__
        if name == "DataNotFoundError":
            return HTTPException(status_code=404, detail=str(exc))
        if name in {"DataConfigurationError", "DataUnavailableError"}:
            return HTTPException(status_code=503, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=503, detail="Alert evaluation is temporarily unavailable.")


@router.get("")
async def get_alert_rules(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    enabled: bool | None = None,
):
    try:
        return {"items": list_rules(_token(access_token), user.id, enabled=enabled)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def post_alert_rule(
    payload: AlertRuleRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": create_rule(_token(access_token), user.id, payload.model_dump())}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/{rule_id}")
async def get_alert_rule(
    rule_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": get_rule(_token(access_token), user.id, rule_id)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.patch("/{rule_id}", dependencies=[Depends(_require_csrf)])
async def patch_alert_rule(
    rule_id: str,
    payload: AlertRulePatch,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        data = {key: value for key, value in payload.model_dump().items() if value is not None}
        return {"item": update_rule(_token(access_token), user.id, rule_id, data)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/{rule_id}/enable", dependencies=[Depends(_require_csrf)])
async def enable_alert_rule(
    rule_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    enabled: bool = Query(...),
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": set_rule_enabled(_token(access_token), user.id, rule_id, enabled)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove_alert_rule(
    rule_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        delete_rule(_token(access_token), user.id, rule_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@router.get("/events/list")
async def get_alert_events(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    unread: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
):
    try:
        return {"items": list_events(_token(access_token), user.id, unread=unread, limit=limit)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/events/evaluate", dependencies=[Depends(_require_csrf)])
async def check_alerts(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"items": await evaluate_rules(_token(access_token), user.id)}
    except Exception as exc:
        raise _map_error(exc) from exc


@router.post("/events/{event_id}/read", dependencies=[Depends(_require_csrf)])
async def read_alert_event(
    event_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": mark_event_read(_token(access_token), user.id, event_id)}
    except Exception as exc:
        raise _map_error(exc) from exc