from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.preferences.models import UserPreferencesRecord


class PreferencesRepositoryError(Exception):
    """Base exception for preference persistence failures."""


class PreferencesConfigurationError(PreferencesRepositoryError):
    """Raised when the Supabase Data API is not configured."""


class PreferencesUnavailableError(PreferencesRepositoryError):
    """Raised when the Supabase Data API cannot be reached."""


class PreferencesRequestError(PreferencesRepositoryError):
    """Raised for a non-retryable persistence failure."""


def _require_config() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise PreferencesConfigurationError("Supabase Data API is not configured.")
    return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key


def _request(
    method: str,
    path: str,
    access_token: str,
    *,
    params: dict[str, str] | None = None,
    payload: Any = None,
    prefer: str | None = None,
) -> httpx.Response:
    base_url, key = _require_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = httpx.request(
            method,
            f"{base_url}/rest/v1/{path}",
            headers=headers,
            params=params,
            json=payload,
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise PreferencesUnavailableError("Database service is temporarily unavailable.") from exc

    if response.status_code in {401, 403}:
        raise PreferencesRequestError("Database authorization failed.")
    if response.status_code >= 500:
        raise PreferencesUnavailableError("Database service is temporarily unavailable.")
    if response.status_code >= 400:
        try:
            detail = response.json().get("message") or response.json().get("details")
        except ValueError:
            detail = None
        raise PreferencesRequestError(str(detail or "Preference persistence failed."))
    return response


def _record(row: dict[str, Any]) -> UserPreferencesRecord:
    return UserPreferencesRecord(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        research_preferences=dict(row["research_preferences"]),
        signal_preferences=dict(row["signal_preferences"]),
        alert_preferences=dict(row["alert_preferences"]),
        market_data_preferences=dict(row["market_data_preferences"]),
        display_preferences=dict(row["display_preferences"]),
        ai_preferences=dict(row["ai_preferences"]),
        privacy_preferences=dict(row["privacy_preferences"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def get_preferences(access_token: str, user_id: str) -> UserPreferencesRecord | None:
    response = _request(
        "GET",
        "user_preferences",
        access_token,
        params={
            "select": "id,user_id,research_preferences,signal_preferences,alert_preferences,market_data_preferences,display_preferences,ai_preferences,privacy_preferences,created_at,updated_at",
            "user_id": f"eq.{user_id}",
            "limit": "1",
        },
    )
    rows = response.json()
    return _record(rows[0]) if rows else None


def upsert_preferences(
    access_token: str,
    user_id: str,
    values: dict[str, Any],
) -> UserPreferencesRecord:
    payload = {"user_id": user_id, **values}
    response = _request(
        "POST",
        "user_preferences?on_conflict=user_id",
        access_token,
        payload=[payload],
        prefer="resolution=merge-duplicates,return=representation,missing=default",
    )
    rows = response.json()
    if not rows:
        raise PreferencesRequestError("Preferences were not saved.")
    return _record(rows[0])
