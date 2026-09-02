from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from app.config import settings
from app.models import Quote, QuoteStatus, ProviderStatus
from app.models.market import FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.base import MarketDataProvider
from app.providers.finnhub import FinnhubProvider
from app.providers.twelve_data import TwelveDataProvider
from app.services.cache import CanonicalMarketCache
from app.symbols import normalize_symbol


@dataclass
class ProviderHealthState:
    consecutive_failures: int = 0
    opened_until: float = 0.0
    last_latency_ms: int | None = None
    last_error: str | None = None

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self.opened_until


class MarketDataOrchestrator:
    """Canonical provider boundary for all market-data reads."""

    def __init__(self, providers: list[MarketDataProvider] | None = None) -> None:
        self.providers = providers or [TwelveDataProvider(), FinnhubProvider(), AlphaVantageProvider()]
        self._health = {provider.name: ProviderHealthState() for provider in self.providers}
        self._lock = Lock()
        self.quote_cache: CanonicalMarketCache[Quote] = CanonicalMarketCache()
        self.candle_cache: CanonicalMarketCache[OHLCVDataset] = CanonicalMarketCache()

    def _state(self, provider: MarketDataProvider) -> ProviderHealthState:
        return self._health[provider.name]

    def _record_success(self, provider: MarketDataProvider, latency_ms: int) -> None:
        with self._lock:
            state = self._state(provider)
            state.consecutive_failures = 0
            state.opened_until = 0.0
            state.last_latency_ms = latency_ms
            state.last_error = None

    def _record_failure(self, provider: MarketDataProvider, error: str, latency_ms: int) -> None:
        with self._lock:
            state = self._state(provider)
            state.consecutive_failures += 1
            state.last_latency_ms = latency_ms
            state.last_error = error
            if state.consecutive_failures >= settings.provider_failure_threshold:
                state.opened_until = time.monotonic() + settings.provider_circuit_cooldown_seconds

    def provider_status(self) -> list[ProviderStatus]:
        return [ProviderStatus(
            provider=provider.name,
            configured=provider.configured,
            reachable=None,
            circuit_open=self._state(provider).circuit_open,
            consecutive_failures=self._state(provider).consecutive_failures,
            last_latency_ms=self._state(provider).last_latency_ms,
            message=("Configured; health is learned from real requests." if provider.configured else "Provider key is not configured."),
        ) for provider in self.providers]

    @staticmethod
    def _fresh_quote(quote: Quote) -> bool:
        return quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED} and quote.price is not None

    @staticmethod
    def _fresh_dataset(dataset: OHLCVDataset) -> bool:
        return dataset.freshness_status in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED} and bool(dataset.completed_candles)

    async def get_quote(self, symbol: str, *, force_refresh: bool = False, excluded_providers: set[str] | None = None) -> Quote:
        mapping = normalize_symbol(symbol)
        key = mapping.internal
        excluded = excluded_providers or set()
        attempts: list[str] = []

        cached = self.quote_cache.get(key, allow_stale=False)
        if cached is not None and not force_refresh and not excluded:
            cached_quote, _ = cached
            return cached_quote.model_copy(update={"cache_hit": True, "latency_ms": 0})

        for provider in self.providers:
            if provider.name in excluded or not provider.configured or self._state(provider).circuit_open:
                continue
            attempts.append(provider.name)
            started = time.perf_counter()
            try:
                quote = await asyncio.wait_for(provider.get_quote(key), timeout=settings.provider_timeout_seconds)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if not self._fresh_quote(quote):
                    self._record_failure(provider, quote.error or "Provider returned unusable quote", latency_ms)
                    continue
                self._record_success(provider, latency_ms)
                quote = quote.model_copy(update={
                    "latency_ms": latency_ms,
                    "provider_attempts": tuple(attempts),
                    "fallback_used": provider.name != self.providers[0].name or bool(excluded),
                    "cache_hit": False,
                })
                self.quote_cache.set(key, quote, settings.quote_cache_seconds, settings.stale_quote_seconds)
                return quote
            except Exception as exc:
                self._record_failure(provider, str(exc), int((time.perf_counter() - started) * 1000))

        cached = self.quote_cache.get(key, allow_stale=True)
        if cached is not None:
            cached_quote, age = cached
            if cached_quote.status == QuoteStatus.STALE or age > settings.quote_cache_seconds:
                return cached_quote.model_copy(update={
                    "status": QuoteStatus.STALE,
                    "freshness_status": FreshnessStatus.STALE,
                    "freshness_age_seconds": max(cached_quote.freshness_age_seconds or 0.0, age),
                    "error": "All live providers were unavailable; serving the last validated market quote.",
                "cache_hit": True,
                "fallback_used": True,
                "provider_attempts": tuple(attempts) or cached_quote.provider_attempts,
                "latency_ms": 0,
                })
            return cached_quote.model_copy(update={
                "cache_hit": True,
                "fallback_used": True,
                "provider_attempts": tuple(attempts) or cached_quote.provider_attempts,
                "latency_ms": 0,
            })

        return Quote(symbol=key, provider_symbol=mapping.twelve_data, status=QuoteStatus.UNAVAILABLE, source=None,
                     error="All configured market-data providers were unavailable and no canonical cache entry exists.",
                     fallback_used=bool(attempts), provider_attempts=tuple(attempts))

    async def get_candles(self, symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date: datetime | None = None, end_date: datetime | None = None, *, excluded_providers: set[str] | None = None) -> OHLCVDataset:
        mapping = normalize_symbol(symbol)
        timeframe = Timeframe(timeframe)
        range_key = "recent" if start_date is None else f"{start_date.isoformat()}:{end_date.isoformat()}"
        key = f"{mapping.internal}|{timeframe.value}|{outputsize}|{range_key}"
        excluded = excluded_providers or set()
        attempts: list[str] = []

        cached = self.candle_cache.get(key, allow_stale=False)
        if cached is not None and not excluded:
            dataset, _ = cached
            return dataset.model_copy(update={"cache_hit": True, "request_latency_ms": 0})

        for provider in self.providers:
            if provider.name in excluded or not provider.configured or self._state(provider).circuit_open:
                continue
            attempts.append(provider.name)
            started = time.perf_counter()
            try:
                dataset = await asyncio.wait_for(provider.get_candles(mapping.internal, timeframe, outputsize, start_date=start_date, end_date=end_date), timeout=max(settings.analysis_timeout_seconds, settings.provider_timeout_seconds))
                latency_ms = int((time.perf_counter() - started) * 1000)
                if not self._fresh_dataset(dataset):
                    self._record_failure(provider, "Provider candle set is stale or incomplete", latency_ms)
                    continue
                self._record_success(provider, latency_ms)
                dataset = dataset.model_copy(update={
                    "request_latency_ms": latency_ms,
                    "provider_attempts": tuple(attempts),
                    "fallback_used": provider.name != self.providers[0].name or bool(excluded),
                    "cache_hit": False,
                })
                self.candle_cache.set(key, dataset, settings.quote_cache_seconds, settings.market_cache_stale_seconds)
                return dataset
            except Exception as exc:
                self._record_failure(provider, str(exc), int((time.perf_counter() - started) * 1000))

        cached = self.candle_cache.get(key, allow_stale=True)
        if cached is not None:
            dataset, age = cached
            if dataset.freshness_status == FreshnessStatus.STALE or age > settings.quote_cache_seconds:
                dataset = dataset.model_copy(update={"freshness_status": FreshnessStatus.STALE, "freshness_age_seconds": max(dataset.freshness_age_seconds or 0.0, age)})
            return dataset.model_copy(update={"fallback_used": True, "cache_hit": True, "cache_age_seconds": age, "provider_attempts": tuple(attempts) or dataset.provider_attempts, "request_latency_ms": 0})

        raise RuntimeError("All configured market-data providers were unavailable and no canonical candle cache entry exists.")


market_data = MarketDataOrchestrator()
