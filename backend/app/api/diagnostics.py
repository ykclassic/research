from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends

from app.api.auth import require_github_actions
from app.config import settings

router = APIRouter(
    prefix="/internal/diagnostics",
    tags=["internal-diagnostics"],
    dependencies=[Depends(require_github_actions)],
)

PROJECT_REF_PATTERN = re.compile(r"^[a-z0-9]{20}$")
DEPLOYMENT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
PROBE_METHOD = "GET /auth/v1/settings (publishable key; read-only)"


def _project_ref_from_url(url: str) -> str | None:
    """Return a project ref only for a canonical HTTPS Supabase origin."""
    if not url or url != url.strip():
        return None
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if (
            parsed.scheme.lower() != "https"
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            return None
    except (ValueError, AttributeError):
        return None

    suffix = ".supabase.co"
    if not hostname.endswith(suffix):
        return None
    candidate = hostname[: -len(suffix)]
    return candidate if PROJECT_REF_PATTERN.fullmatch(candidate) else None


def _deployment_sha() -> str | None:
    value = os.getenv("RENDER_GIT_COMMIT", "")
    return value.lower() if DEPLOYMENT_SHA_PATTERN.fullmatch(value) else None


def _result(project_ref: str | None, status: str, reason_code: str) -> dict[str, str | None]:
    return {
        "project_ref": project_ref,
        "deployment_sha": _deployment_sha(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe_method": PROBE_METHOD,
        "status": status,
        "reason_code": reason_code,
    }


@router.get("/database")
def database_diagnostic() -> dict[str, str | None]:
    """Protected, read-only target check; never return credentials, URLs, bodies, or exceptions.

    The endpoint is restricted to a narrowly scoped, verified GitHub Actions OIDC
    identity. It uses the application's configured publishable key, not the
    service-role key, and only performs GET against Supabase Auth settings.
    """
    expected_ref = settings.supabase_expected_production_project_ref
    if not expected_ref or not expected_ref.strip():
        return _result(None, "failed", "expected_target_missing")
    if not PROJECT_REF_PATTERN.fullmatch(expected_ref):
        return _result(None, "failed", "expected_target_invalid")

    project_ref = _project_ref_from_url(settings.supabase_url)
    if project_ref is None:
        return _result(None, "failed", "supabase_url_invalid")
    if project_ref != expected_ref:
        return _result(project_ref, "failed", "target_mismatch")
    if not settings.supabase_publishable_key or not settings.supabase_publishable_key.strip():
        return _result(project_ref, "failed", "publishable_key_missing")

    try:
        # Supabase Auth's settings endpoint is a read-only GET and uses the
        # same URL + publishable-key HTTP pattern as app/services/supabase_auth.py.
        # Redirects are not followed; response content is deliberately discarded.
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/settings",
            headers={"apikey": settings.supabase_publishable_key},
            timeout=settings.http_timeout_seconds,
        )
    except httpx.RequestError:
        return _result(project_ref, "failed", "probe_unavailable")
    except Exception:
        return _result(project_ref, "failed", "probe_unavailable")

    if response.status_code in {401, 403}:
        return _result(project_ref, "failed", "probe_authorization_failed")
    if not 200 <= response.status_code < 300:
        return _result(project_ref, "failed", "probe_http_error")
    return _result(project_ref, "passed", "probe_succeeded")
