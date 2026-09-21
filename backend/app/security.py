from __future__ import annotations

import re


# Vercel generates stable production, preview, and branch deployment origins for
# this project. Keep the pattern narrow to the project's known hostname family;
# never use a wildcard origin for credentialed requests.
VERCEL_ORIGIN_REGEX = r"https://research(?:-tech-solut-hub|-[a-z0-9-]+-tech-solut-hub|-dusky-six)\\.vercel\\.app"


def configured_origins(cors_origins: str) -> set[str]:
    return {origin.strip().rstrip("/") for origin in cors_origins.split(",") if origin.strip()}


def is_allowed_web_origin(origin: str | None, cors_origins: str) -> bool:
    if not origin:
        return False
    normalized_origin = origin.strip().rstrip("/")
    if normalized_origin in configured_origins(cors_origins):
        return True
    return bool(re.fullmatch(VERCEL_ORIGIN_REGEX, normalized_origin))
