from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.preferences.repository import (
    PreferencesConfigurationError,
    PreferencesRequestError,
    PreferencesRepositoryError,
    PreferencesUnavailableError,
)
from app.preferences.schemas import MessageResponse, UserPreferences, UserPreferencesResponse
from app.preferences.service import preferences_service
from app.services.supabase_data import DataServiceError, delete_all_watchlists, delete_research_history

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
    except PreferencesRepositoryError as exc:
        raise _map_error(exc) from exc


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
