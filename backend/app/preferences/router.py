from __future__ import annotations

import io
import json
import zipfile
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.preferences.repository import (
    PreferencesConfigurationError,
    PreferencesRequestError,
    PreferencesRepositoryError,
    PreferencesUnavailableError,
)
from app.preferences.schemas import MessageResponse, UserPreferences, UserPreferencesResponse
from app.preferences.service import preferences_service
from app.services.entitlement import FeatureNotEntitledError, UsageLimitExceededError, consume_usage, require_feature\nfrom app.services.privacy_data import account_data, apply_retention, history_csv, watchlists_csv
from app.services.supabase_data import DataServiceError, delete_all_watchlists, delete_research_history
from app.services.system_status import system_status

router = APIRouter(prefix="/api/preferences", tags=["preferences"])


def _access_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return token


def _map_error(exc: PreferencesRepositoryError) -> HTTPException:
    if isinstance(exc, PreferencesConfigurationError):
        return HTTPException(status_code=503, detail="Settings persistence is not configured.")
    if isinstance(exc, PreferencesUnavailableError):
        return HTTPException(status_code=503, detail="Settings persistence is temporarily unavailable.")
    if isinstance(exc, PreferencesRequestError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail="Unable to process settings.")


def _map_data_error(exc: DataServiceError) -> HTTPException:
    return HTTPException(status_code=503, detail="Database service is temporarily unavailable.")


def _response(record) -> UserPreferencesResponse:
    return UserPreferencesResponse(
        id=record.id,
        user_id=record.user_id,
        research_preferences=record.research_preferences,
        signal_preferences=record.signal_preferences,
        alert_preferences=record.alert_preferences,
        market_data_preferences=record.market_data_preferences,
        display_preferences=record.display_preferences,
        ai_preferences=record.ai_preferences,
        privacy_preferences=record.privacy_preferences,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=UserPreferencesResponse)
async def get_preferences(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> UserPreferencesResponse:
    try:
        record = preferences_service.get_or_create(_access_token(access_token), user.id)
        return _response(record)
    except PreferencesRepositoryError as exc:
        raise _map_error(exc) from exc


@router.put("", response_model=UserPreferencesResponse, dependencies=[Depends(_require_csrf)])
async def update_preferences(
    payload: UserPreferences,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> UserPreferencesResponse:
    try:
        record = preferences_service.update(_access_token(access_token), user.id, payload)
        return _response(record)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PreferencesRepositoryError as exc:
        raise _map_error(exc) from exc


@router.post("/reset", response_model=UserPreferencesResponse, dependencies=[Depends(_require_csrf)])
async def reset_preferences(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> UserPreferencesResponse:
    try:
        record = preferences_service.reset(_access_token(access_token), user.id)
        return _response(record)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PreferencesRepositoryError as exc:
        raise _map_error(exc) from exc


@router.get("/system-status")
async def get_system_status(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return await system_status(_access_token(access_token), user.id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="System diagnostics are temporarily unavailable.") from exc


@router.delete("/data/research-history", response_model=MessageResponse, dependencies=[Depends(_require_csrf)])
async def clear_research_history(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> MessageResponse:
    try:
        delete_research_history(_access_token(access_token), user.id)
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc
    return MessageResponse(message="Research history deleted.")


@router.delete("/data/watchlists", response_model=MessageResponse, dependencies=[Depends(_require_csrf)])
async def clear_watchlists(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> MessageResponse:
    try:
        delete_all_watchlists(_access_token(access_token), user.id)
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc
    return MessageResponse(message="All watchlists deleted.")


def _download(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.get("/data/export/research")
async def export_research(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> Response:
    token = _access_token(access_token)
    try:
        reports = history_csv(token, user.id, record_type="REPORT")
        history = history_csv(token, user.id)
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("reports.csv", reports)
            archive.writestr("research_history.csv", history)
        return _download(bundle.getvalue(), "research_export.zip", "application/zip")
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc


@router.get("/data/export/reports")
async def export_reports(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> Response:
    token = _access_token(access_token)\n    try:\n        require_feature(token, user.id, "exports")\n        consume_usage(token, user.id, "exports", 1)\n        return _download(history_csv(_access_token(access_token), user.id, record_type="REPORT"), "reports.csv", "text/csv; charset=utf-8")
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc


@router.get("/data/export/watchlists")
async def export_watchlists(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> Response:
    token = _access_token(access_token)\n    try:\n        require_feature(token, user.id, "exports")\n        consume_usage(token, user.id, "exports", 1)\n        return _download(watchlists_csv(_access_token(access_token), user.id), "watchlists.csv", "text/csv; charset=utf-8")
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc


@router.get("/data/export/account")
async def export_account_data(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> Response:
    try:
        payload = account_data(_access_token(access_token), user.id)
        payload["account"].update({"email": user.email, "created_at": user.created_at, "email_confirmed_at": user.email_confirmed_at, "last_sign_in_at": user.last_sign_in_at})
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return _download(content, "account_data.json", "application/json")
    except DataServiceError as exc:
        raise _map_data_error(exc) from exc


@router.delete("/data/cache", response_model=MessageResponse, dependencies=[Depends(_require_csrf)])
async def clear_server_cache(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> MessageResponse:
    _ = user
    _ = _access_token(access_token)
    from app.providers.orchestrator import market_data
    from app.services.market_data_health import market_data_health

    market_data.quote_cache.clear()
    market_data.candle_cache.clear()
    market_data_health.clear_diagnostics_cache()
    return MessageResponse(message="Server-side market-data cache cleared. Persistent research history was not modified.")
