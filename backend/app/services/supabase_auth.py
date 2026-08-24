from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class AuthServiceError(Exception):
    """Base exception for Supabase Auth failures."""


class AuthConfigurationError(AuthServiceError):
    """Raised when Supabase Auth configuration is missing."""


def _require_config() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise AuthConfigurationError("Supabase Auth is not configured.")
    return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key


def _headers() -> dict[str, str]:
    _, key = _require_config()
    return {"apikey": key, "Content-Type": "application/json"}


def _raise_auth_error(response: httpx.Response) -> None:
    try:
        payload: Any = response.json()
        message = payload.get("msg") or payload.get("message") or payload.get("error_description")
    except ValueError:
        message = None
    raise AuthServiceError(message or "Authentication request failed.")


def sign_up(email: str, password: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    response = httpx.post(f"{base_url}/auth/v1/signup", headers=_headers(), json={"email": email, "password": password}, timeout=settings.http_timeout_seconds)
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def sign_in(email: str, password: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    response = httpx.post(f"{base_url}/auth/v1/token?grant_type=password", headers=_headers(), json={"email": email, "password": password}, timeout=settings.http_timeout_seconds)
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def get_user(access_token: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    response = httpx.get(f"{base_url}/auth/v1/user", headers={**_headers(), "Authorization": f"Bearer {access_token}"}, timeout=settings.http_timeout_seconds)
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def sign_out(access_token: str) -> None:
    base_url, _ = _require_config()
    response = httpx.post(f"{base_url}/auth/v1/logout", headers={**_headers(), "Authorization": f"Bearer {access_token}"}, timeout=settings.http_timeout_seconds)
    if response.status_code >= 400:
        _raise_auth_error(response)
