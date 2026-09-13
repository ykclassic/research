from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.models.market import CompletenessStatus, FreshnessStatus
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import freshness_for_age
from app.symbols import normalize_symbol


async def get_forex_quote(symbol: str) -> Quote | None:
    """Recover a major FX quote without consuming the normal Twelve Data quote budget.

    Alpha Vantage is preferred when configured because its currency exchange-rate
    endpoint is a separate provider budget. Twelve Data's direct exchange-rate
    endpoint remains the second recovery path when Alpha Vantage is unavailable.
    """
    mapping = normalize_symbol(symbol)
    if mapping.asset_class != "forex":
        return None

    if settings.alpha_vantage_api_key.strip():
        try:
            quote = await AlphaVantageProvider().get_quote(mapping.internal)
            if quote.status != QuoteStatus.UNAVAILABLE:
                return quote.model_copy(update={"fallback_used": True})
        except Exception:
            pass

    if not settings.twelve_data_api_key.strip():
        return None

    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.provider_timeout_seconds)) as client:
            response = await client.get(
                "https://api.twelvedata.com/exchange_rate",
                params={"symbol": mapping.internal, "apikey": settings.twelve_data_api_key},
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            return None
        rate = float(payload.get("rate", 0))
        timestamp = payload.get("timestamp")
        if rate <= 0 or timestamp is None:
            return None
        provider_timestamp = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        observed_at = datetime.now(timezone.utc)
        age = max(0.0, (observed_at - provider_timestamp).total_seconds())
        freshness = freshness_for_age(age, settings.stale_quote_seconds)
        status = {
            FreshnessStatus.FRESH: QuoteStatus.LIVE,
            FreshnessStatus.DELAYED: QuoteStatus.DELAYED,
            FreshnessStatus.STALE: QuoteStatus.STALE,
        }.get(freshness, QuoteStatus.UNAVAILABLE)
        return Quote(
            symbol=mapping.internal,
            provider_symbol=mapping.twelve_data,
            price=rate,
            timestamp=provider_timestamp,
            provider_timestamp=provider_timestamp,
            observed_at=observed_at,
            source="twelve_data_exchange_rate",
            status=status,
            latency_ms=int((datetime.now(timezone.utc) - started).total_seconds() * 1000),
            cache_hit=False,
            freshness_status=freshness,
            freshness_age_seconds=age,
            completeness_status=CompletenessStatus.COMPLETE,
            fallback_used=True,
            provider_attempts=("twelve_data_exchange_rate",),
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None
