from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import Quote, QuoteStatus
from app.providers.base import MarketDataProvider
from app.symbols import normalize_symbol


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"
    base_url = "https://finnhub.io/api/v1/quote"

    async def get_quote(self, internal_symbol: str) -> Quote:
        mapping = normalize_symbol(internal_symbol)
        if not settings.finnhub_api_key:
            return Quote(symbol=mapping.internal, provider_symbol=mapping.finnhub, source=self.name, status=QuoteStatus.UNAVAILABLE, error="FINNHUB_API_KEY is not configured.")

        started = time.perf_counter()
        try:
            timeout = httpx.Timeout(settings.http_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self.base_url, params={"symbol": mapping.finnhub, "token": settings.finnhub_api_key})
            response.raise_for_status()
            payload = response.json()
            raw_price = payload.get("c")
            raw_timestamp = payload.get("t")
            if raw_price is None or raw_timestamp is None:
                raise ValueError("Finnhub response lacks a current price or authoritative timestamp.")
            price = float(raw_price)
            provider_ts = datetime.fromtimestamp(float(raw_timestamp), tz=timezone.utc)
            if price <= 0:
                raise ValueError("Finnhub returned a non-positive price.")
            observed_at = datetime.now(timezone.utc)
            age = (observed_at - provider_ts).total_seconds()
            if age < -60 or age > settings.stale_quote_seconds:
                raise ValueError(f"Finnhub quote is stale or timestamp is invalid: age={age:.2f}s.")
            return Quote(symbol=mapping.internal, provider_symbol=mapping.finnhub, price=price, timestamp=provider_ts, provider_timestamp=provider_ts, observed_at=observed_at, source=self.name, status=QuoteStatus.LIVE, latency_ms=int((time.perf_counter()-started)*1000), cache_hit=False)
        except (httpx.HTTPError, ValueError, TypeError, OverflowError) as exc:
            return Quote(symbol=mapping.internal, provider_symbol=mapping.finnhub, source=self.name, status=QuoteStatus.UNAVAILABLE, latency_ms=int((time.perf_counter()-started)*1000), error=str(exc), cache_hit=False)

    async def get_candles(self, *args, **kwargs):
        raise RuntimeError("Finnhub candle fallback is disabled for the free-tier project scope.")

    async def health(self) -> bool:
        return bool(settings.finnhub_api_key)
