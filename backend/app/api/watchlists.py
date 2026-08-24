from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.auth import CSRF_COOKIE, _require_csrf, get_current_user
from app.models import UserResponse
from app.services.supabase_data import (
    DataConfigurationError,
    DataConflictError,
    DataNotFoundError,
    DataRequestError,
    DataServiceError,
    DataUnavailableError,
    add_symbol,
    create_watchlist,
    delete_watchlist,
    get_or_create_default_watchlist,
    list_watchlists,
    remove_symbol,
    update_watchlist,
)
from app.symbols import normalize_symbol

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WatchlistUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


def _map_error(exc: DataServiceError) -> HTTPException:
    if isinstance(exc, DataConfigurationError):
        return HTTPException(status_code=503, detail="Database service is not configured.")
    if isinstance(exc, DataUnavailableError):
        return HTTPException(status_code=503, detail="Database service is temporarily unavailable.")
    if isinstance(exc, DataNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DataConflictError):
        return HTTPException(status_code=409, detail="The watchlist already contains that item or name.")
    return HTTPException(status_code=400, detail=str(exc))


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


@router.get("")
async def get_watchlists(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"watchlists": get_or_create_default_watchlist(_token(access_token), user.id)}
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def create(
    payload: WatchlistCreate,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    name = " ".join(payload.name.strip().split())
    if not name:
        raise HTTPException(status_code=422, detail="Watchlist name cannot be empty.")
    try:
        return create_watchlist(_token(access_token), user.id, name)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.patch("/{watchlist_id}", dependencies=[Depends(_require_csrf)])
async def rename(
    watchlist_id: str,
    payload: WatchlistUpdate,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    name = " ".join(payload.name.strip().split())
    if not name:
        raise HTTPException(status_code=422, detail="Watchlist name cannot be empty.")
    try:
        return update_watchlist(_token(access_token), user.id, watchlist_id, name)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def delete(
    watchlist_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        delete_watchlist(_token(access_token), user.id, watchlist_id)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.post("/{watchlist_id}/symbols", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def add(
    watchlist_id: str,
    payload: SymbolRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        symbol = normalize_symbol(payload.symbol).internal
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return add_symbol(_token(access_token), user.id, watchlist_id, symbol)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.delete("/{watchlist_id}/symbols/{symbol:path}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove(
    watchlist_id: str,
    symbol: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        normalized = normalize_symbol(symbol).internal
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        remove_symbol(_token(access_token), user.id, watchlist_id, normalized)
    except DataServiceError as exc:
        raise _map_error(exc) from exc
