from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.preferences.service import preferences_service
from app.services.market_data_health import market_data_health


APPLICATION_VERSION = "1.18.0"


async def system_status(access_token: str, user_id: str) -> dict[str, Any]:
    """Return user-safe application state backed by live service checks."""
    checked_at = datetime.now(timezone.utc)
    market_task = asyncio.create_task(market_data_health.snapshot())
    database_status = "OPERATIONAL"
    try:
        preferences_service.get_or_create(access_token, user_id)
    except Exception:
        database_status = "DEGRADED"

    try:
        market = await market_task
        market_providers = market.get("providers", [])
        market_operational = any(item.get("status") == "OPERATIONAL" for item in market_providers)
        market_status = "OPERATIONAL" if market_operational else "DEGRADED"
        last_sync = market.get("checked_at")
        cache = market.get("cache", {})
        cache_status = str(cache.get("status", "UNKNOWN"))
        cache_health = "HEALTHY" if cache_status in {"AVAILABLE", "EMPTY"} else "DEGRADED"
    except Exception:
        market = None
        market_status = "UNAVAILABLE"
        last_sync = None
        cache_health = "UNKNOWN"
        cache = {"status": "UNKNOWN", "quote_entries": 0, "candle_entries": 0}
        market_providers = []
        database_status = "DEGRADED"

    return {
        "checked_at": checked_at,
        "application_version": APPLICATION_VERSION,
        "environment": settings.app_env,
        "api_connection": {"status": "CONNECTED", "message": "Application API is responding."},
        "authentication": {"status": "OPERATIONAL", "message": "Authenticated user session is valid."},
        "database": {"status": database_status, "message": "User-scoped database access is responding." if database_status == "OPERATIONAL" else "User-scoped database access could not be verified."},
        "market_data_service": {"status": market_status, "message": "At least one market-data provider passed live diagnostics." if market_status == "OPERATIONAL" else "No market-data provider currently passed live diagnostics."},
        "last_synchronization": last_sync,
        "cache": {"status": cache_health, "quote_entries": cache.get("quote_entries", 0), "candle_entries": cache.get("candle_entries", 0)},
        "market_data": {"checked_at": market.get("checked_at") if market else None, "cached_result": market.get("cached_result") if market else False, "providers": market_providers},
    }
