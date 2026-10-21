from __future__ import annotations

import os
import re
from urllib.parse import urlparse
from typing import Literal

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
PROBE_KIND = "read_only_postgrest_billing_plans_limit_1"


def _project_ref_from_url(url: str) -> str | None:
    """Accept only a canonical HTTPS Supabase project origin.

    Do not infer a trusted project from a URL that changes transport, adds
    credentials/ports, or redirects the REST path through an unexpected URL.
    """
    try:
        parsed = urlparse(url.strip())
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


@router.get("/database")
def database_diagnostic() -> dict[str, str | bool | None]:
    """Protected, read-only diagnostic for the backend's effective DB target.

    Never return credentials, URLs, headers, database addresses, row contents,
    or raw exception text. Access is restricted to trusted GitHub Actions OIDC.
    """
    configured = bool(settings.supabase_url.strip() and settings.supabase_service_role_key.strip())
    project_ref = _project_ref_from_url(settings.supabase_url) if settings.supabase_url else None
    probe: Literal["ok", "failed", "not_configured"] = "not_configured"

    if configured and project_ref == EXPECTED_PRODUCTION_PROJECT_REF:
        try:
            # The service-role credential remains server-side. Limit the read to
            # a harmless catalogue row and discard the response contents.
            service_request(
                "GET",
                "billing_plans",
                params={"select": "id", "limit": "1"},
            )
            probe = "ok"
        except (DataServiceError, ValueError, TypeError):
            probe = "failed"
        except Exception:
            # Fail closed while keeping provider/connection details private.
            probe = "failed"
    elif configured:
        # Do not send even the service-role credential to an unexpected project.
        probe = "failed"

    return {
        "configured": configured,
        "project_ref": project_ref,
        "database_probe": probe,
        "probe_kind": PROBE_KIND,
        "deployment_commit": os.getenv("RENDER_GIT_COMMIT"),
    }
