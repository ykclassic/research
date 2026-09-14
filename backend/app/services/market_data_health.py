from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models import QuoteStatus
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.finnhub import FinnhubProvider
from app.providers.kraken_public import KrakenPublicProvider
from app.providers.twelve_data import TwelveDataProvider
from app.services.quote_service import market_data


@dataclass(frozen=True)
class HealthProbe:
    role: str
    provider: str
    status: str
    configured: bool
    last_successful_request: datetime | None
    last_request: datetime | None
    latency_ms: int | None
    validation_status: str
    candle_completeness: str
    provenance_available: bool
    fallback_status: str
    cache_status: str
    message: str


class MarketDataHealthService:
    """Run bounded, real provider probes for the Settings diagnostics panel.

    A provider is marked operational only after a real request succeeds and its
    response contains usable market data plus provenance. Results are cached
    briefly so opening Settings does not create a provider request storm.
    """

    CACHE_SECONDS = 30.0

    def __init__(self) -> None:
        self._cached: dict[str, HealthProbe] | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def _run_quote_probe(
        self,
        role: str,
        provider: Any,
        symbol: str,
        fallback_status: str = "NOT_USED",
    ) -> HealthProbe:
        requested_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        if not provider.configured:
            return HealthProbe(
                role=role,
                provider=provider.name,
                status="UNAVAILABLE",
                configured=False,
                last_successful_request=None,
                last_request=requested_at,
                latency_ms=0,
                validation_status="NOT_CHECKED",
                candle_completeness="NOT_CHECKED",
                provenance_available=False,
                fallback_status="NOT_CONFIGURED",
                cache_status="UNKNOWN",
                message="Provider is not configured on the server.",
            )
        try:
            quote = await asyncio.wait_for(provider.get_quote(symbol), timeout=settings.provider_timeout_seconds)
            latency_ms = int((time.perf_counter() - started) * 1000)
            usable = quote.status != QuoteStatus.UNAVAILABLE and quote.price is not None
            provenance = bool(quote.source and quote.provider_symbol and quote.provider_timestamp)
            validation = "PASSED" if usable else "FAILED"
            status = "OPERATIONAL" if usable and provenance else "DEGRADED"
            return HealthProbe(
                role=role,
                provider=provider.name,
                status=status,
                configured=True,
                last_successful_request=datetime.now(timezone.utc) if usable else None,
                last_request=requested_at,
                latency_ms=latency_ms,
                validation_status=validation,
                candle_completeness="NOT_CHECKED",
                provenance_available=provenance,
                fallback_status=fallback_status,
                cache_status="AVAILABLE" if market_data.quote_cache.size() > 0 else "EMPTY",
                message="Live provider response validated." if usable else (quote.error or "Provider returned no usable quote."),
            )
        except Exception as exc:
            return HealthProbe(
                role=role,
                provider=provider.name,
                status="UNAVAILABLE",
                configured=True,
                last_successful_request=None,
                last_request=requested_at,
                latency_ms=int((time.perf_counter() - started) * 1000),
                validation_status="FAILED",
                candle_completeness="NOT_CHECKED",
                provenance_available=False,
                fallback_status=fallback_status,
                cache_status="AVAILABLE" if market_data.quote_cache.size() > 0 else "EMPTY",
                message=str(exc),
            )

    async def snapshot(self, *, force_refresh: bool = False) -> dict[str, Any]:
        async with self._lock:
            now = time.monotonic()
            if self._cached is not None and not force_refresh and now - self._cached_at < self.CACHE_SECONDS:
                return self._serialize(self._cached, cached=True)

            probes = await asyncio.gather(
                self._run_quote_probe("primary", TwelveDataProvider(), "BTC/USD"),
                self._run_quote_probe("crypto_fallback", KrakenPublicProvider(), "BTC/USD", "AVAILABLE"),
                self._run_quote_probe("forex", AlphaVantageProvider(), "EUR/USD"),
                self._run_quote_probe("stocks", FinnhubProvider(), "AAPL"),
            )
            self._cached = {probe.role: probe for probe in probes}
            self._cached_at = time.monotonic()
            return self._serialize(self._cached, cached=False)

    @staticmethod
    def _serialize(probes: dict[str, HealthProbe], *, cached: bool) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc)
        provider_items = [
            {
                "role": probe.role,
                "provider": probe.provider,
                "status": probe.status,
                "configured": probe.configured,
                "last_successful_request": probe.last_successful_request,
                "last_request": probe.last_request,
                "latency_ms": probe.latency_ms,
                "validation_status": probe.validation_status,
                "candle_completeness": probe.candle_completeness,
                "provenance_available": probe.provenance_available,
                "fallback_status": probe.fallback_status,
                "cache_status": probe.cache_status,
                "message": probe.message,
            }
            for probe in probes.values()
        ]
        return {
            "checked_at": checked_at,
            "cached_result": cached,
            "cache_ttl_seconds": MarketDataHealthService.CACHE_SECONDS,
            "providers": provider_items,
            "cache": {
                "quote_entries": market_data.quote_cache.size(),
                "candle_entries": market_data.candle_cache.size(),
                "status": "AVAILABLE" if market_data.quote_cache.size() or market_data.candle_cache.size() else "EMPTY",
            },
            "security": {
                "credentials_exposed": False,
                "message": "Provider credentials and server configuration are never included in health responses.",
            },
        }


market_data_health = MarketDataHealthService()
