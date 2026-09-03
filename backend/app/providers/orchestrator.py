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
from app.providers.errors import ProviderErrorCode, classify_provider_error, error_label
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
    last_error_code: ProviderErrorCode | None = None
    credits_used: int | None = None
    credits_remaining: int | None = None
    usage_observed_at: datetime | None = None

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self.opened_until


class MarketDataOrchestrator:
    """Canonical provider boundary for all market-data reads."""

    def __init__(self, providers: list[MarketDataProvider] | None = None) -> None:
        # Order is part of the production data contract: Twelve Data -> Alpha Vantage -> Finnhub.
        self.providers = providers or [TwelveDataProvider(), AlphaVantageProvider(), FinnhubProvider()]
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
            state.last_error_code = None
            usage = provider.usage
            if usage is not None:
                state.credits_used = usage.credits_used
                state.credits_remaining = usage.credits_remaining
                state.usage_observed_at = usage.observed_at

    def _record_failure(
        self,
        provider: MarketDataProvider,
        error: str,
        latency_ms: int,
        error_code: ProviderErrorCode,
    ) -> None:
        with self._lock:
            state = self._state(provider)
            state.last_latency_ms = latency_ms
            state.last_error = error
            state.last_error_code = error_code
            usage = provider.usage
            if usage is not None:
                state.credits_used = usage.credits_used
                state.credits_remaining = usage.credits_remaining
                state.usage_observed_at = usage.observed_at
            # Circuit breaking still applies to unknown provider failures; symbol
            # unsupported is isolated to that symbol and must not disable the feed.
            if error_code != ProviderErrorCode.SYMBOL_UNSUPPORTED:
                state.consecutive_failures += 1
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
            last_error=self._state(provider).last_error,
            last_error_code=self._state(provider).last_error_code,
            credits_used=self._state(provider).credits_used,
            credits_remaining=self._state(provider).credits_remaining,
            usage_observed_at=self._state(provider).usage_observed_at,
            message=("Configured; health is learned from real requests." if provider.configured else "Provider key is not configured."),
        ) for provider in self.providers]

    @staticmethod
    def _fresh_quote(quote: Quote) -> bool:
        return quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED} and quote.price is not None

    @staticmethod
    def _fresh_dataset(dataset: OHLCVDataset) -> bool:
        return dataset.freshness_status in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED} and bool(dataset.completed_candles)

    @staticmethod
    def _normalized_error_code(quote: Quote) -> ProviderErrorCode:
        if quote.error_code is not None:
            return quote.error_code
        return classify_provider_error(message=quote.error)

    @staticmethod
    def _error_text(code: ProviderErrorCode, detail: str | None = None) -> str:
        label = error_label(code)
        return f"{label}: {detail}" if detail else label

    async def get_quote(self, symbol: str, *, force_refresh: bool = False, excluded_providers: set[str] | None = None) -> Quote:
        results = await self.get_quotes([symbol], force_refresh=force_refresh, excluded_providers=excluded_providers)
        return results[0]

    async def get_quotes(
        self,
        symbols: list[str],
        *,
        force_refresh: bool = False,
        excluded_providers: set[str] | None = None,
    ) -> list[Quote]:
        if not symbols:
            return []
        excluded = excluded_providers or set()
        mappings = [normalize_symbol(symbol) for symbol in symbols]
        unique_keys = list(dict.fromkeys(mapping.internal for mapping in mappings))
        results: dict[str, Quote] = {}
        remaining: list[str] = []
        diagnostics: dict[str, list[str]] = {key: [] for key in unique_keys}

        for key in unique_keys:
            cached = self.quote_cache.get(key, allow_stale=False)
            if cached is not None and not force_refresh and not excluded:
                cached_quote, _ = cached
                results[key] = cached_quote.model_copy(update={"cache_hit": True, "latency_ms": 0})
            else:
                remaining.append(key)

        for provider in self.providers:
            if not remaining:
                break
            if provider.name in excluded or not provider.configured or self._state(provider).circuit_open:
                continue

            candidates = list(remaining)
            started = time.perf_counter()
            try:
                quotes = await asyncio.wait_for(
                    provider.get_quotes(candidates),
                    timeout=settings.provider_timeout_seconds,
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                by_symbol = {quote.symbol: quote for quote in quotes}
                successful = 0
                provider_failure_codes: list[ProviderErrorCode] = []

                for key in candidates:
                    diagnostics[key].append(provider.name)
                    quote = by_symbol.get(key)
                    if quote is None:
                        provider_failure_codes.append(ProviderErrorCode.PROVIDER_UNAVAILABLE)
                        continue
                    code = self._normalized_error_code(quote)
                    if self._fresh_quote(quote):
                        successful += 1
                        enriched = quote.model_copy(update={
                            "latency_ms": latency_ms,
                            "provider_attempts": tuple(diagnostics[key]),
                            "fallback_used": provider.name != self.providers[0].name or bool(excluded),
                            "cache_hit": False,
                        })
                        results[key] = enriched
                        self.quote_cache.set(key, enriched, settings.quote_cache_seconds, settings.stale_quote_seconds)
                    else:
                        provider_failure_codes.append(code)

                if successful:
                    self._record_success(provider, latency_ms)
                elif provider_failure_codes:
                    # Record one provider-level failure per batch, not one per symbol.
                    code = provider_failure_codes[0]
                    detail = next((by_symbol[key].error for key in candidates if key in by_symbol and by_symbol[key].error), "Provider returned no usable quotes")
                    self._record_failure(provider, detail, latency_ms, code)

                remaining = [key for key in remaining if key not in results]
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                code = classify_provider_error(exc)
                for key in candidates:
                    diagnostics[key].append(provider.name)
                self._record_failure(provider, str(exc), latency_ms, code)
                remaining = [key for key in remaining if key not in results]

        output: dict[str, Quote] = {}
        for key in unique_keys:
            if key in results:
                output[key] = results[key]
                continue
            cached = self.quote_cache.get(key, allow_stale=True)
            mapping = normalize_symbol(key)
            if cached is not None:
                cached_quote, age = cached
                if cached_quote.status == QuoteStatus.STALE or age > settings.quote_cache_seconds:
                    output[key] = cached_quote.model_copy(update={
                        "status": QuoteStatus.STALE,
                        "freshness_status": FreshnessStatus.STALE,
                        "freshness_age_seconds": max(cached_quote.freshness_age_seconds or 0.0, age),
                        "error": "All live providers were unavailable; serving the last validated market quote.",
                        "error_code": ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE,
                        "cache_hit": True,
                        "fallback_used": True,
                        "provider_attempts": tuple(diagnostics[key]) or cached_quote.provider_attempts,
                        "latency_ms": 0,
                    })
                else:
                    output[key] = cached_quote.model_copy(update={
                        "cache_hit": True,
                        "fallback_used": True,
                        "provider_attempts": tuple(diagnostics[key]) or cached_quote.provider_attempts,
                        "latency_ms": 0,
                    })
                continue

            attempts = diagnostics[key]
            provider_errors = []
            for provider in self.providers:
                state = self._state(provider)
                if provider.name in attempts and state.last_error:
                    provider_errors.append(f"{provider.name}={error_label(state.last_error_code)}")
            detail = "; ".join(provider_errors) or "No configured provider produced a usable quote."
            output[key] = Quote(
                symbol=key,
                provider_symbol=mapping.twelve_data,
                status=QuoteStatus.UNAVAILABLE,
                source=None,
                error=f"{self._error_text(ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE)}: {detail}",
                error_code=ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE,
                fallback_used=bool(attempts),
                provider_attempts=tuple(attempts),
            )

        return [output[normalize_symbol(symbol).internal] for symbol in symbols]

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
                    self._record_failure(provider, "Provider candle set is stale or incomplete", latency_ms, ProviderErrorCode.PROVIDER_UNAVAILABLE)
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
                code = classify_provider_error(exc)
                self._record_failure(provider, str(exc), int((time.perf_counter() - started) * 1000), code)

        cached = self.candle_cache.get(key, allow_stale=True)
        if cached is not None:
            dataset, age = cached
            if dataset.freshness_status == FreshnessStatus.STALE or age > settings.quote_cache_seconds:
                dataset = dataset.model_copy(update={"freshness_status": FreshnessStatus.STALE, "freshness_age_seconds": max(dataset.freshness_age_seconds or 0.0, age)})
            return dataset.model_copy(update={"fallback_used": True, "cache_hit": True, "cache_age_seconds": age, "provider_attempts": tuple(attempts) or dataset.provider_attempts, "request_latency_ms": 0})

        raise RuntimeError("All configured market-data providers were unavailable and no canonical candle cache entry exists.")


market_data = MarketDataOrchestrator()
