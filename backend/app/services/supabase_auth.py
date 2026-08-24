from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class AuthServiceError(Exception):
    """Base exception for Supabase Auth failures."""


class AuthConfigurationError(AuthServiceError):
    """Raised when Supabase Auth configuration is missing."""


class AuthInvalidCredentialsError(AuthServiceError):
    """Raised when Supabase rejects the supplied credentials."""


class AuthEmailNotConfirmedError(AuthServiceError):
    """Raised when Supabase requires email confirmation before sign-in."""


class AuthUnavailableError(AuthServiceError):
    """Raised when the Supabase Auth service cannot be reached or is unavailable."""


class AuthResetTokenError(AuthServiceError):
    """Raised when a password-reset token is invalid or expired."""


def _require_config() -> tuple[str, str]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise AuthConfigurationError("Supabase Auth is not configured.")
    return settings.supabase_url.rstrip("/"), settings.supabase_publishable_key


def _headers() -> dict[str, str]:
    _, key = _require_config()
    return {"apikey": key, "Content-Type": "application/json"}


def _response_message(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
        if isinstance(payload, dict):
            message = (
                payload.get("msg")
                or payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
            )
            if message:
                return str(message)
    except ValueError:
        pass
    return "Authentication request failed."


def _raise_auth_error(response: httpx.Response) -> None:
    message = _response_message(response)
    normalized = message.lower()

    if response.status_code in {400, 401}:
        if "email not confirmed" in normalized or "email_not_confirmed" in normalized:
            raise AuthEmailNotConfirmedError(message)
        raise AuthInvalidCredentialsError(message)

    if response.status_code == 429 or response.status_code >= 500:
        raise AuthUnavailableError(message)

    raise AuthServiceError(message)


def sign_up(email: str, password: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    try:
        response = httpx.post(
            f"{base_url}/auth/v1/signup",
            headers=_headers(),
            json={"email": email, "password": password},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def sign_in(email: str, password: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    try:
        response = httpx.post(
            f"{base_url}/auth/v1/token?grant_type=password",
            headers=_headers(),
            json={"email": email, "password": password},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def request_password_reset(email: str) -> None:
    base_url, _ = _require_config()
    redirect_to = settings.auth_password_reset_redirect_url.strip()
    if not redirect_to:
        raise AuthConfigurationError("Password reset redirect URL is not configured.")
    try:
        response = httpx.post(
            f"{base_url}/auth/v1/recover",
            headers=_headers(),
            json={"email": email, "redirect_to": redirect_to},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code >= 400:
        _raise_auth_error(response)


def update_password(access_token: str, new_password: str) -> dict[str, Any]:
    if not access_token.strip():
        raise AuthResetTokenError("Password reset link is invalid or expired.")
    base_url, _ = _require_config()
    try:
        response = httpx.put(
            f"{base_url}/auth/v1/user",
            headers={**_headers(), "Authorization": f"Bearer {access_token}"},
            json={"password": new_password},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code in {401, 403}:
        raise AuthResetTokenError("Password reset link is invalid or expired.")
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def get_user(access_token: str) -> dict[str, Any]:
    base_url, _ = _require_config()
    try:
        response = httpx.get(
            f"{base_url}/auth/v1/user",
            headers={**_headers(), "Authorization": f"Bearer {access_token}"},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code >= 400:
        _raise_auth_error(response)
    return response.json()


def sign_out(access_token: str) -> None:
    base_url, _ = _require_config()
    try:
        response = httpx.post(
            f"{base_url}/auth/v1/logout",
            headers={**_headers(), "Authorization": f"Bearer {access_token}"},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError as exc:
        raise AuthUnavailableError("Authentication service is unavailable.") from exc
    if response.status_code >= 400:
        _raise_auth_error(response)
