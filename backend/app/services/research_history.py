from __future__ import annotations

from typing import Any

from app.services.supabase_data import (
    DataConflictError,
    DataRequestError,
    _request,
)


def _row(response) -> dict[str, Any]:
    rows = response.json()
    if not rows:
        raise DataRequestError("Research history record was not created or found.")
    return rows[0]


def create_history_record(
    access_token: str,
    user_id: str,
    *,
    record_type: str,
    symbol: str | None = None,
    query: str | None = None,
    title: str | None = None,
    payload: dict[str, Any] | None = None,
    saved: bool = False,
) -> dict[str, Any]:
    if record_type not in {"REPORT", "SEARCH", "AI_ANALYSIS"}:
        raise ValueError("Unsupported research history record type.")
    response = _request(
        "POST",
        "research_history",
        access_token,
        json={
            "user_id": user_id,
            "record_type": record_type,
            "symbol": symbol,
            "query": query,
            "title": title,
            "payload": payload or {},
            "saved": saved,
        },
        prefer="return=representation",
    )
    return _row(response)


def list_history(
    access_token: str,
    user_id: str,
    *,
    record_type: str | None = None,
    symbol: str | None = None,
    saved: bool | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params = {
        "select": "id,user_id,record_type,symbol,query,title,payload,saved,created_at,updated_at",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": str(max(1, min(limit, 100))),
    }
    if record_type:
        params["record_type"] = f"eq.{record_type}"
    if symbol:
        params["symbol"] = f"eq.{symbol}"
    if saved is not None:
        params["saved"] = f"eq.{str(saved).lower()}"
    response = _request("GET", "research_history", access_token, params=params)
    return response.json()


def get_history_record(access_token: str, user_id: str, history_id: str) -> dict[str, Any]:
    response = _request(
        "GET",
        "research_history",
        access_token,
        params={
            "select": "id,user_id,record_type,symbol,query,title,payload,saved,created_at,updated_at",
            "id": f"eq.{history_id}",
            "user_id": f"eq.{user_id}",
        },
    )
    return _row(response)


def set_saved(access_token: str, user_id: str, history_id: str, saved: bool) -> dict[str, Any]:
    response = _request(
        "PATCH",
        "research_history",
        access_token,
        params={"id": f"eq.{history_id}", "user_id": f"eq.{user_id}"},
        json={"saved": saved},
        prefer="return=representation",
    )
    return _row(response)


def delete_history_record(access_token: str, user_id: str, history_id: str) -> None:
    _request(
        "DELETE",
        "research_history",
        access_token,
        params={"id": f"eq.{history_id}", "user_id": f"eq.{user_id}"},
    )


def add_note(access_token: str, user_id: str, history_id: str, note: str) -> dict[str, Any]:
    owned = get_history_record(access_token, user_id, history_id)
    if not owned:
        raise DataRequestError("Research history record was not found.")
    response = _request(
        "POST",
        "research_notes",
        access_token,
        json={"user_id": user_id, "history_id": history_id, "note": note.strip()},
        prefer="return=representation",
    )
    return _row(response)


def list_notes(access_token: str, user_id: str, history_id: str) -> list[dict[str, Any]]:
    response = _request(
        "GET",
        "research_notes",
        access_token,
        params={
            "select": "id,history_id,note,created_at,updated_at",
            "user_id": f"eq.{user_id}",
            "history_id": f"eq.{history_id}",
            "order": "created_at.desc",
        },
    )
    return response.json()


def delete_note(access_token: str, user_id: str, note_id: str) -> None:
    _request(
        "DELETE",
        "research_notes",
        access_token,
        params={"id": f"eq.{note_id}", "user_id": f"eq.{user_id}"},
    )
