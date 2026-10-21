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
# No currently established PostgREST resource can be queried with only the
# publishable key: the known research_snapshots table revokes anon access and
# grants SELECT to authenticated users only. GitHub OIDC is not a Supabase user
# JWT, so never pretend a publishable-key-only request verifies the data path.
PROBE_METHOD = "unavailable: existing PostgREST resources require an authenticated user JWT"


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


def _result(project_ref: str | None, deployment_sha: str | None, status: str, reason_code: str) -> dict[str, str | None]:
    return {
        "project_ref": project_ref,
        "deployment_sha": deployment_sha,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe_method": PROBE_METHOD,
        "status": status,
        "reason_code": reason_code,
    }


@router.get("/database")
def database_diagnostic() -> dict[str, str | None]:
    """Protected, fail-closed identity diagnostic; does not claim DB access is verified.

    The route requires a verified, narrowly scoped GitHub Actions OIDC identity.
    The configured publishable key is deliberately not used to probe an
    authenticated-only PostgREST table. A real read-only Data API probe remains
    unavailable until an approved authenticated data-access method is designed.
    No request is made to Supabase from this endpoint in its current state.
    """
    expected_ref = settings.supabase_expected_production_project_ref
    if not expected_ref or not expected_ref.strip():
        return _result(None, _deployment_sha(), "failed", "expected_target_missing")
    if not PROJECT_REF_PATTERN.fullmatch(expected_ref):
        return _result(None, _deployment_sha(), "failed", "expected_target_invalid")

    project_ref = _project_ref_from_url(settings.supabase_url)
    if project_ref is None:
        return _result(None, _deployment_sha(), "failed", "supabase_url_invalid")
    if project_ref != expected_ref:
        return _result(project_ref, _deployment_sha(), "failed", "target_mismatch")

    deployment_value = os.getenv("RENDER_GIT_COMMIT", "")
    deployment_sha = _deployment_sha()
    if not deployment_value:
        return _result(project_ref, None, "failed", "deployment_identity_missing")
    if deployment_sha is None:
        return _result(project_ref, None, "failed", "deployment_identity_invalid")

    if not settings.supabase_publishable_key or not settings.supabase_publishable_key.strip():
        return _result(project_ref, deployment_sha, "failed", "publishable_key_missing")

    # A publishable key maps to the anon role without a Supabase user JWT.
    # Repository migrations explicitly revoke anon access to research_snapshots
    # and grant SELECT to authenticated users. Do not issue an unverified probe.
    return _result(project_ref, deployment_sha, "failed", "probe_unavailable")
