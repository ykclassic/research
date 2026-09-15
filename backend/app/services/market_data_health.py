from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models import QuoteStatus
from app.models.market import Timeframe
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
    """Run bounded, real provider probes for the Settings diagnostics panel."""

    CACHE_SECONDS = 30.0
    HEALTH_CANDLE_LIMIT = 50

    def __init__(self) -> None:
        self._cached: dict[str, HealthProbe] | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    def clear_diagnostics_cache(self) -> None:
        self._cached = None
        self._cached_at = 0.0

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
                role,
                provider.name,
                "UNAVAILABLE",
                False,
                None,
                requested_at,
                0,
                "NOT_CHECKED",
                "NOT_CHECKED",
                False,
                "NOT_CONFIGURED",
                "UNKNOWN",
                "Provider is not configured on the server.",
            )
        try:
            quote = await asyncio.wait_for(
                provider.get_quote(symbol),
                timeout=settings.provider_timeout_seconds,
            )
            usable = quote.status != QuoteStatus.UNAVAILABLE and quote.price is not None
            provenance = bool(
                quote.source and quote.provider_symbol and quote.provider_timestamp
            )
            if not usable or not provenance:
                return HealthProbe(
                    role,
                    provider.name,
                    "DEGRADED" if usable else "UNAVAILABLE",
                    True,
                    None,
                    requested_at,
                    int((time.perf_counter() - started) * 1000),
                    "PASSED" if usable else "FAILED",
                    "NOT_CHECKED",
                    provenance,
                    fallback_status,
                    "AVAILABLE" if market_data.quote_cache.size() > 0 else "EMPTY",
                    quote.error or "Quote validation or provenance check failed.",
                )
            candle = await asyncio.wait_for(
                provider.get_candles(
                    symbol,
                    Timeframe.HOUR_1,
                    self.HEALTH_CANDLE_LIMIT,
                ),
                timeout=settings.provider_timeout_seconds,
            )
            complete = bool(candle.completed_candles) and candle.completeness_status.value == "COMPLETE"
            return HealthProbe(
                role,
                provider.name,
                "OPERATIONAL" if complete else "DEGRADED",
                True,
                datetime.now(timezone.utc) if complete else None,
                requested_at,
                int((time.perf_counter() - started) * 1000),
                "PASSED",
                "PASSED" if complete else "FAILED",
                provenance,
                fallback_status,
                "AVAILABLE" if market_data.quote_cache.size() or market_data.candle_cache.size() else "EMPTY",
                "Quote and completed-candle response validated."
                if complete
                else "Quote passed, but candle completeness validation failed.",
            )
        except Exception as exc:
            return HealthProbe(
                role,
                provider.name,
                "UNAVAILABLE",
                True,
                None,
                requested_at,
                int((time.perf_counter() - started) * 1000),
                "FAILED",
                "FAILED",
                False,
                fallback_status,
                "AVAILABLE" if market_data.quote_cache.size() or market_data.candle_cache.size() else "EMPTY",
                str(exc),
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

    def _serialize(self, probes: dict[str, HealthProbe], *, cached: bool) -> dict[str, Any]:
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
        quote_count = market_data.quote_cache.size()
        candle_count = market_data.candle_cache.size()
        return {
            "checked_at": checked_at,
            "cached_result": cached,
            "cache_ttl_seconds": self.CACHE_SECONDS,
            "providers": provider_items,
            "cache": {
                "quote_entries": quote_count,
                "candle_entries": candle_count,
                "status": "AVAILABLE" if quote_count or candle_count else "EMPTY",
            },
            "security": {
                "credentials_exposed": False,
                "message": "Provider credentials and server configuration are never included in health responses.",
            },
        }


market_data_health = MarketDataHealthService()
