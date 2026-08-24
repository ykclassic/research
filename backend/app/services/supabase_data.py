from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class DataServiceError(Exception):
    """Base exception for Supabase Data API failures."""


class DataConfigurationError(DataServiceError):
    """Raised when Supabase Data API configuration is missing."""


class DataUnavailableError(DataServiceError):
    """Raised when the Supabase Data API cannot be reached."""


class DataConflictError(DataServiceError):
    """Raised when a requested resource conflicts with existing data."""


class DataNotFoundError(DataServiceError):
    """Raised when a requested resource does not exist for the current user."""


class DataRequestError(DataServiceError):
    """Raised for non-retryable Data API failures."""


def _require_config() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise DataConfigurationError("Supabase Data API is not configured.")
    return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key


def _headers(access_token: str, *, prefer: str | None = None) -> dict[str, str]:
    _, key = _require_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _message(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
        if isinstance(payload, dict):
            return str(
                payload.get("message")
                or payload.get("details")
                or payload.get("hint")
                or payload.get("error")
                or "Supabase Data API request failed."
            )
    except ValueError:
        pass
    return "Supabase Data API request failed."


def _request(
    method: str,
    path: str,
    access_token: str,
    *,
    params: dict[str, str] | None = None,
    json: Any = None,
    prefer: str | None = None,
) -> httpx.Response:
    base_url, _ = _require_config()
    try:
        response = httpx.request(
            method,
            f"{base_url}/rest/v1/{path}",
            headers=_headers(access_token, prefer=prefer),
            params=params,
            json=json,
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise DataUnavailableError("Database service is temporarily unavailable.") from exc

    if response.status_code in {401, 403}:
        raise DataRequestError("Database authorization failed.")
    if response.status_code == 404:
        raise DataNotFoundError("Requested resource was not found.")
    if response.status_code == 409:
        raise DataConflictError(_message(response))
    if response.status_code >= 500:
        raise DataUnavailableError("Database service is temporarily unavailable.")
    if response.status_code >= 400:
        raise DataRequestError(_message(response))
    return response


def list_watchlists(access_token: str, user_id: str) -> list[dict[str, Any]]:
    response = _request(
        "GET",
        "watchlists",
        access_token,
        params={
            "select": "id,user_id,name,created_at,updated_at,watchlist_items(id,symbol,created_at)",
            "user_id": f"eq.{user_id}",
            "order": "created_at.asc",
        },
    )
    return response.json()


def create_watchlist(access_token: str, user_id: str, name: str) -> dict[str, Any]:
    response = _request(
        "POST",
        "watchlists",
        access_token,
        json={"user_id": user_id, "name": name},
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise DataRequestError("Watchlist was not created.")
    return rows[0]


def get_or_create_default_watchlist(access_token: str, user_id: str) -> list[dict[str, Any]]:
    watchlists = list_watchlists(access_token, user_id)
    if watchlists:
        return watchlists
    try:
        create_watchlist(access_token, user_id, "My Watchlist")
    except DataConflictError:
        pass
    return list_watchlists(access_token, user_id)


def update_watchlist(access_token: str, user_id: str, watchlist_id: str, name: str) -> dict[str, Any]:
    response = _request(
        "PATCH",
        "watchlists",
        access_token,
        params={"id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}"},
        json={"name": name},
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise DataNotFoundError("Watchlist was not found.")
    return rows[0]


def delete_watchlist(access_token: str, user_id: str, watchlist_id: str) -> None:
    response = _request(
        "DELETE",
        "watchlists",
        access_token,
        params={"id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}"},
    )
    if response.status_code not in {200, 204}:
        raise DataRequestError("Watchlist was not deleted.")


def add_symbol(access_token: str, user_id: str, watchlist_id: str, symbol: str) -> dict[str, Any]:
    owned = _request(
        "GET",
        "watchlists",
        access_token,
        params={"select": "id", "id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}"},
    ).json()
    if not owned:
        raise DataNotFoundError("Watchlist was not found.")

    response = _request(
        "POST",
        "watchlist_items",
        access_token,
        json={"watchlist_id": watchlist_id, "symbol": symbol},
        prefer="return=representation",
    )
    rows = response.json()
    if not rows:
        raise DataRequestError("Symbol was not added.")
    return rows[0]


def remove_symbol(access_token: str, user_id: str, watchlist_id: str, symbol: str) -> None:
    owned = _request(
        "GET",
        "watchlists",
        access_token,
        params={"select": "id", "id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}"},
    ).json()
    if not owned:
        raise DataNotFoundError("Watchlist was not found.")

    _request(
        "DELETE",
        "watchlist_items",
        access_token,
        params={"watchlist_id": f"eq.{watchlist_id}", "symbol": f"eq.{symbol}"},
    )
