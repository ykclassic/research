from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends

from app.api.auth import require_github_actions
from app.config import settings
from app.services.supabase_data import DataServiceError, service_request

router = APIRouter(
    prefix="/internal/diagnostics",
    tags=["internal-diagnostics"],
    dependencies=[Depends(require_github_actions)],
)

PROJECT_REF_PATTERN = re.compile(r"^[a-z0-9]{20}$")
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
PROBE_METHOD = "postgrest_service_role_read_only_select_billing_plans_limit_1"


def _project_ref_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None

    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        return None

    suffix = ".supabase.co"
    if not hostname.endswith(suffix):
        return None
    candidate = hostname[: -len(suffix)]
    return candidate if PROJECT_REF_PATTERN.fullmatch(candidate) else None


def _failure(project_ref: str | None, deployment_sha: str | None, reason: str) -> dict[str, str | None]:
    return {
        "project_ref": project_ref,
        "deployment_sha": deployment_sha,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe_method": PROBE_METHOD,
        "status": "failed",
        "reason_code": reason,
    }


@router.get("/database")
def database_diagnostic() -> dict[str, str | None]:
    """Protected, read-only check of the configured production Supabase target.

    GitHub Actions OIDC authenticates the caller. The database probe separately
    uses the backend's configured service-role credential for one fixed,
    read-only PostgREST SELECT. No credential, URL, header, row content, or
    exception detail is returned.
    """
    configured_url = settings.supabase_url.strip()
    project_ref = _project_ref_from_url(configured_url) if configured_url else None
    expected_ref = settings.supabase_expected_production_project_ref.strip()
    raw_sha = os.getenv("RENDER_GIT_COMMIT", "").strip()
    deployment_sha = raw_sha.lower() if COMMIT_SHA_PATTERN.fullmatch(raw_sha) else None

    if not expected_ref:
        return _failure(project_ref, deployment_sha, "expected_target_missing")
    if not PROJECT_REF_PATTERN.fullmatch(expected_ref):
        return _failure(project_ref, deployment_sha, "expected_target_invalid")
    if project_ref is None:
        return _failure(None, deployment_sha, "supabase_url_invalid")
    if project_ref != expected_ref:
        return _failure(project_ref, deployment_sha, "target_mismatch")
    if not raw_sha:
        return _failure(project_ref, None, "deployment_identity_missing")
    if deployment_sha is None:
        return _failure(project_ref, None, "deployment_identity_invalid")
    if not settings.supabase_service_role_key.strip():
        return _failure(project_ref, deployment_sha, "service_role_key_missing")

    try:
        response = service_request(
            "GET",
            "billing_plans",
            params={"select": "id", "limit": "1"},
        )
        rows = response.json()
        if not isinstance(rows, list):
            return _failure(project_ref, deployment_sha, "probe_response_invalid")
    except (DataServiceError, ValueError, TypeError):
        return _failure(project_ref, deployment_sha, "probe_failed")
    except Exception:
        return _failure(project_ref, deployment_sha, "probe_failed")

    return {
        "project_ref": project_ref,
        "deployment_sha": deployment_sha,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "probe_method": PROBE_METHOD,
        "status": "passed",
        "reason_code": None,
    }
