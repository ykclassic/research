from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, _require_csrf, get_current_user
from app.services.research_history import (
    add_note,
    create_history_record,
    delete_history_record,
    delete_note,
    get_history_record,
    list_history,
    list_notes,
    set_saved,
)
from app.services.supabase_data import DataServiceError

router = APIRouter(prefix="/api/research-history", tags=["research-history"])


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=5000)


def _token(access_token: str | None) -> str:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return access_token


def _map_error(exc: DataServiceError) -> HTTPException:
    status_code = 503 if exc.__class__.__name__ in {"DataConfigurationError", "DataUnavailableError"} else 400
    if exc.__class__.__name__ == "DataNotFoundError":
        status_code = 404
    if exc.__class__.__name__ == "DataConflictError":
        status_code = 409
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("")
async def history(
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
    record_type: str | None = Query(default=None, pattern="^(REPORT|SEARCH|AI_ANALYSIS)$"),
    symbol: str | None = Query(default=None, min_length=1, max_length=32),
    saved: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
):
    try:
        return {"items": list_history(_token(access_token), user.id, record_type=record_type, symbol=symbol, saved=saved, limit=limit)}
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.get("/{history_id}")
async def detail(
    history_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        record = get_history_record(_token(access_token), user.id, history_id)
        return {"item": record, "notes": list_notes(_token(access_token), user.id, history_id)}
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.post("/{history_id}/save", dependencies=[Depends(_require_csrf)])
async def save(
    history_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": set_saved(_token(access_token), user.id, history_id, True)}
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.delete("/{history_id}/save", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def unsave(
    history_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        set_saved(_token(access_token), user.id, history_id, False)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.delete("/{history_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def delete(
    history_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        delete_history_record(_token(access_token), user.id, history_id)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.post("/{history_id}/notes", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def create_note(
    history_id: str,
    payload: NoteRequest,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"note": add_note(_token(access_token), user.id, history_id, payload.note)}
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[Depends(_require_csrf)])
async def remove_note(
    note_id: str,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
) -> None:
    try:
        delete_note(_token(access_token), user.id, note_id)
    except DataServiceError as exc:
        raise _map_error(exc) from exc


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(_require_csrf)])
async def create_search(
    payload: dict,
    user: Annotated[UserResponse, Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="mr_access_token")] = None,
):
    try:
        return {"item": create_history_record(_token(access_token), user.id, record_type="SEARCH", symbol=payload.get("symbol"), query=payload.get("query"), title=payload.get("title"), payload=payload.get("payload") or {})}
    except DataServiceError as exc:
        raise _map_error(exc) from exc
