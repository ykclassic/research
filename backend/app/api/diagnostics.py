from __future__ import annotations

import os
import re
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
EXPECTED_PRODUCTION_PROJECT_REF = "rprgjfvfttxydhbekuoc"
PROBE_KIND = "probe_unavailable_no_authorized_postgrest_path"


def _project_ref_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None

    # A service-role key must never be sent to a non-TLS, credential-bearing,
    # redirected-path, or otherwise ambiguous endpoint.
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


@router.get("/database")
def database_diagnostic() -> dict[str, str | bool | None]:
    """Protected, read-only diagnostic for the backend's effective DB target.

    Never return credentials, URLs, headers, database addresses, row contents,
    or raw exception text. Access is restricted to trusted GitHub Actions OIDC.
    """
    configured = bool(settings.supabase_url.strip() and settings.supabase_service_role_key.strip())
    project_ref = _project_ref_from_url(settings.supabase_url) if settings.supabase_url else None
    # Deliberately do not probe PostgREST with a service-role key until a
    # separately reviewed, authenticated read-only path is approved. GitHub
    # OIDC is not a Supabase user JWT and a publishable key is not sufficient.
    return {
        "configured": configured,
        "project_ref": project_ref,
        "database_probe": "probe_unavailable",
        "probe_kind": PROBE_KIND,
        "deployment_commit": os.getenv("RENDER_GIT_COMMIT"),
    }
