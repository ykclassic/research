from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from jwt import PyJWKClient
from pydantic import BaseModel, EmailStr, Field

from app.config import settings
from app.services.supabase_auth import (
    AuthConfigurationError,
    AuthEmailNotConfirmedError,
    AuthInvalidCredentialsError,
    AuthResetTokenError,
    AuthServiceError,
    AuthUnavailableError,
    get_user,
    request_password_reset,
    sign_in,
    sign_out,
    sign_up,
    update_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
SESSION_COOKIE = "mr_access_token"
CSRF_COOKIE = "mr_csrf"
CSRF_HEADER = "X-CSRF-Token"
GITHUB_OIDC_ALGORITHMS = ("RS256",)
GITHUB_OIDC_EVENTS = {"schedule", "workflow_dispatch"}


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    created_at: str | None = None


class MessageResponse(BaseModel):
    message: str


@lru_cache(maxsize=1)
def _github_oidc_jwks_client() -> PyJWKClient:
    return PyJWKClient(settings.github_oidc_jwks_url, cache_jwk_set=True, lifespan=300)


def _cookie_secure() -> bool:
    return settings.app_env.lower() in {"production", "prod"}


def _csrf_token(access_token: str) -> str:
    return hmac.new(
        settings.csrf_secret.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _set_auth_cookies(response: Response, access_token: str) -> str:
    csrf_token = _csrf_token(access_token)
    secure = _cookie_secure()
    response.set_cookie(SESSION_COOKIE, access_token, max_age=settings.auth_session_seconds, httponly=True, secure=secure, samesite="none" if secure else "lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=settings.auth_session_seconds, httponly=False, secure=secure, samesite="none" if secure else "lax", path="/")
    response.headers[CSRF_HEADER] = csrf_token
    return csrf_token


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def _configured_origins() -> set[str]:
    return {origin.strip().rstrip("/") for origin in settings.cors_origins.split(",") if origin.strip()}


def _require_csrf(
    csrf_cookie: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
    csrf_header: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
    access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    origin: Annotated[str | None, Header(alias="Origin")] = None,
) -> None:
    if not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF validation failed.")
    if settings.app_env.lower() in {"production", "prod"} and origin:
        normalized_origin = origin.rstrip("/")
        if normalized_origin not in _configured_origins():
            raise HTTPException(status_code=403, detail="CSRF origin validation failed.")
    cookie_valid = bool(csrf_cookie and secrets.compare_digest(csrf_cookie, csrf_header))
    signed_valid = bool(access_token and secrets.compare_digest(_csrf_token(access_token), csrf_header))
    if not (cookie_valid or signed_valid):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def _map_user(payload: dict[str, Any]) -> UserResponse:
    user = payload.get("user", payload)
    return UserResponse(id=str(user["id"]), email=user["email"], created_at=user.get("created_at"))


def _auth_error(exc: AuthServiceError) -> HTTPException:
    if isinstance(exc, AuthConfigurationError):
        return HTTPException(status_code=503, detail="Authentication service is not configured.")
    if isinstance(exc, AuthUnavailableError):
        return HTTPException(status_code=503, detail="Authentication service is temporarily unavailable.")
    if isinstance(exc, AuthEmailNotConfirmedError):
        return HTTPException(status_code=403, detail="Email address has not been confirmed.")
    if isinstance(exc, AuthInvalidCredentialsError):
        return HTTPException(status_code=401, detail="Invalid email or password.")
    if isinstance(exc, AuthResetTokenError):
        return HTTPException(status_code=400, detail="Password reset link is invalid or expired.")
    return HTTPException(status_code=401, detail="Authentication failed.")


def _validate_github_oidc_claims(claims: dict[str, Any]) -> None:
    expected_workflow_refs = {
        f"{settings.github_oidc_repository}/{workflow}@{settings.github_oidc_ref}"
        for workflow in settings.trusted_oidc_workflows
    }
    repository = claims.get("repository")
    ref = claims.get("ref")
    workflow_ref = claims.get("workflow_ref")
    event_name = claims.get("event_name")
    if repository != settings.github_oidc_repository:
        raise HTTPException(status_code=403, detail="GitHub OIDC repository is not trusted.")
    if ref != settings.github_oidc_ref:
        raise HTTPException(status_code=403, detail="GitHub OIDC ref is not trusted.")
    if workflow_ref not in expected_workflow_refs:
        raise HTTPException(status_code=403, detail="GitHub OIDC workflow is not trusted.")
    if event_name in GITHUB_OIDC_EVENTS:
        return
    if event_name == "push" and workflow_ref in expected_workflow_refs:
        return
    raise HTTPException(status_code=403, detail="GitHub OIDC event is not trusted.")


def _verify_github_oidc_token(token: str) -> None:
    try:
        signing_key = _github_oidc_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=list(GITHUB_OIDC_ALGORITHMS), audience=settings.github_oidc_audience, issuer=settings.github_oidc_issuer, options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        _validate_github_oidc_claims(claims)
    except HTTPException:
        raise
    except (jwt.PyJWTError, OSError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid GitHub Actions OIDC token.") from exc


def get_current_user(access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> UserResponse:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return _map_user(get_user(access_token))
    except AuthServiceError as exc:
        raise _auth_error(exc) from exc


def get_current_user_or_github_actions(authorization: Annotated[str | None, Header(alias="Authorization")] = None, access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> UserResponse | None:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Invalid Authorization header.")
        _verify_github_oidc_token(token.strip())
        return None
    return get_current_user(access_token)


def require_github_actions(authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="GitHub Actions OIDC authentication required.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid Authorization header.")
    _verify_github_oidc_token(token.strip())


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials) -> UserResponse:
    try:
        payload = sign_up(credentials.email.strip().lower(), credentials.password)
    except AuthServiceError as exc:
        detail = str(exc)
        code = 503 if isinstance(exc, (AuthConfigurationError, AuthUnavailableError)) else 400
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


@router.get("/csrf")
async def csrf(response: Response, access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> MessageResponse:
    if not access_token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    token = _set_auth_cookies(response, access_token)
    response.headers[CSRF_HEADER] = token
    return MessageResponse(message="CSRF token issued.")


@router.post("/password-reset/request", response_model=MessageResponse)
async def password_reset_request(payload: PasswordResetRequest) -> MessageResponse:
    try:
        request_password_reset(payload.email.strip().lower())
    except AuthConfigurationError as exc:
        raise _auth_error(exc) from exc
    except AuthUnavailableError as exc:
        raise _auth_error(exc) from exc
    except AuthServiceError:
        pass
    return MessageResponse(message="If an account exists for that email, a password reset link has been sent.")


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def password_reset_confirm(payload: PasswordResetConfirm) -> MessageResponse:
    try:
        update_password(payload.access_token, payload.password)
    except AuthServiceError as exc:
        raise _auth_error(exc) from exc
    return MessageResponse(message="Password updated successfully. You can now sign in with your new password.")


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[UserResponse, Depends(get_current_user)]) -> UserResponse:
    return user


@router.post("/logout", response_model=None, status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_csrf)])
async def logout(response: Response, access_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> None:
    if access_token:
        try:
            sign_out(access_token)
        except AuthServiceError:
            pass
    _clear_auth_cookies(response)
