from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.services.supabase_auth import (
    AuthConfigurationError,
    AuthServiceError,
    get_user,
    sign_in,
    sign_out,
    sign_up,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
SESSION_COOKIE = "mr_access_token"
CSRF_COOKIE = "mr_csrf"


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: str | None = None


def _cookie_secure() -> bool:
    return settings.app_env.lower() in {"production", "prod"}


def _set_auth_cookies(response: Response, access_token: str) -> None:
    csrf_token = secrets.token_urlsafe(32)
    secure = _cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=settings.auth_session_seconds,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.auth_session_seconds,
        httponly=False,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _require_csrf(
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def _map_user(payload: dict[str, Any]) -> UserResponse:
    user = payload.get("user", payload)
    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        created_at=user.get("created_at"),
    )


def _auth_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AuthConfigurationError):
        return HTTPException(status_code=503, detail="Authentication service is not configured.")
    return HTTPException(status_code=401, detail="Invalid email or password.")


def get_current_user(
    access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> UserResponse:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return _map_user(get_user(access_token))
    except AuthServiceError as exc:
        raise _auth_error(exc) from exc


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials) -> UserResponse:
    """Create an account without creating an authenticated application session.

    Registration and authentication are deliberately separate operations. The
    caller must explicitly use /login to establish the session cookies.
    """
    try:
        payload = sign_up(credentials.email.strip().lower(), credentials.password)
    except AuthServiceError as exc:
        detail = str(exc)
        code = 503 if isinstance(exc, AuthConfigurationError) else 400
        if "already" in detail.lower() or "registered" in detail.lower():
            code = 409
        raise HTTPException(status_code=code, detail=detail) from exc

    return _map_user(payload)


@router.post("/login", response_model=UserResponse)
async def login(credentials: Credentials, response: Response) -> UserResponse:
    try:
        payload = sign_in(credentials.email.strip().lower(), credentials.password)
    except AuthServiceError as exc:
        raise _auth_error(exc) from exc
    access_token = payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication did not return a session.")
    _set_auth_cookies(response, access_token)
    return _map_user(payload)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    return user


@router.post(
    "/logout",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_csrf)],
)
async def logout(
    response: Response,
    access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if access_token:
        try:
            sign_out(access_token)
        except AuthServiceError:
            pass
    _clear_auth_cookies(response)
