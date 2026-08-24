from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.services.auth import (
    authenticate_user,
    create_session,
    create_user,
    get_user_by_session,
    revoke_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE = "mr_session"
CSRF_COOKIE = "mr_csrf"


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: str


def _cookie_secure() -> bool:
    return settings.app_env.lower() in {"production", "prod"}


def _set_auth_cookies(response: Response, session_token: str) -> None:
    csrf_token = secrets.token_urlsafe(32)
    secure = _cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")


def get_current_user(
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> UserResponse:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = get_user_by_session(session_token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return UserResponse(**user)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials, response: Response) -> UserResponse:
    email = credentials.email.strip().lower()
    try:
        user = create_user(email, credentials.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    session_token, _ = create_session(user["id"])
    _set_auth_cookies(response, session_token)
    return UserResponse(**user)


@router.post("/login", response_model=UserResponse)
async def login(credentials: Credentials, response: Response) -> UserResponse:
    email = credentials.email.strip().lower()
    user = authenticate_user(email, credentials.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    session_token, _ = create_session(user["id"])
    _set_auth_cookies(response, session_token)
    return UserResponse(**user)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_csrf)])
async def logout(
    response: Response,
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if session_token:
        revoke_session(session_token)
    _clear_auth_cookies(response)
