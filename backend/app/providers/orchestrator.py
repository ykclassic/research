from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
from app.services.market_sessions import is_market_open
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
    quote_budget_remaining: int | None = None
    daily_quote_budget_remaining: int | None = None

    @property
    def circuit_open(self) -> bool:
        return time.monotonic() < self.opened_until


class MarketDataOrchestrator:
    """Canonical provider boundary for all market-data reads."""

    def __init__(self, providers: list[MarketDataProvider] | None = None) -> None:
        # Provider order is intentionally unchanged in Phase 1. Phase 2 owns routing order.
        self.providers = providers or [TwelveDataProvider(), AlphaVantageProvider(), FinnhubProvider()]
        self._health = {provider.name: ProviderHealthState() for provider in self.providers}
        self._lock = Lock()
        self._twelve_data_minute_window_started = time.monotonic()
        self._twelve_data_minute_reserved = 0
        self._twelve_data_daily_date = datetime.now(timezone.utc).date()
        self._twelve_data_daily_reserved = 0
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
            # Only actual provider failures may advance the circuit breaker.
            # Semantic quote states (LIVE/DELAYED/MARKET_CLOSED/STALE) are not failures.
            if error_code != ProviderErrorCode.SYMBOL_UNSUPPORTED:
                state.consecutive_failures += 1
                if state.consecutive_failures >= settings.provider_failure_threshold:
                    state.opened_until = time.monotonic() + settings.provider_circuit_cooldown_seconds

    def _available_twelve_data_quote_budget(self, provider: MarketDataProvider) -> int:
        """Return a conservative quote budget for the current minute/day."""
        now = time.monotonic()
        today = datetime.now(timezone.utc).date()
        with self._lock:
            if now - self._twelve_data_minute_window_started >= 60:
                self._twelve_data_minute_window_started = now
                self._twelve_data_minute_reserved = 0
            if today != self._twelve_data_daily_date:
                self._twelve_data_daily_date = today
                self._twelve_data_daily_reserved = 0

            minute_remaining = max(0, settings.twelve_data_quote_minute_budget - self._twelve_data_minute_reserved)
            daily_remaining = max(0, settings.twelve_data_quote_daily_budget - self._twelve_data_daily_reserved)
            available = min(minute_remaining, daily_remaining)
            usage = provider.usage
            if usage is not None and usage.credits_remaining is not None and usage.observed_at is not None:
                usage_age = (datetime.now(timezone.utc) - usage.observed_at).total_seconds()
                if 0 <= usage_age < 60:
                    available = min(available, max(0, usage.credits_remaining))

            state = self._state(provider)
            state.quote_budget_remaining = available
            state.daily_quote_budget_remaining = daily_remaining
            return available

    def _reserve_twelve_data_quote_budget(self, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._twelve_data_minute_reserved += count
            self._twelve_data_daily_reserved += count
            state = self._health.get("twelve_data")
            if state is not None:
                state.quote_budget_remaining = max(0, settings.twelve_data_quote_minute_budget - self._twelve_data_minute_reserved)
                state.daily_quote_budget_remaining = max(0, settings.twelve_data_quote_daily_budget - self._twelve_data_daily_reserved)

    def provider_status(self) -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []
        for provider in self.providers:
            state = self._state(provider)
            quote_budget_remaining = state.quote_budget_remaining
            daily_quote_budget_remaining = state.daily_quote_budget_remaining
            if provider.name == "twelve_data":
                quote_budget_remaining = self._available_twelve_data_quote_budget(provider)
                daily_quote_budget_remaining = state.daily_quote_budget_remaining
            statuses.append(ProviderStatus(
                provider=provider.name,
                configured=provider.configured,
                reachable=None,
                circuit_open=state.circuit_open,
                consecutive_failures=state.consecutive_failures,
                last_latency_ms=state.last_latency_ms,
                last_error=state.last_error,
                last_error_code=state.last_error_code,
                credits_used=state.credits_used,
                credits_remaining=state.credits_remaining,
                usage_observed_at=state.usage_observed_at,
                quote_budget_remaining=quote_budget_remaining,
                daily_quote_budget_remaining=daily_quote_budget_remaining,
                message=("Configured; health is learned from real requests." if provider.configured else "Provider key is not configured."),
            ))
        return statuses

    @staticmethod
    def _fresh_quote(quote: Quote) -> bool:
        return quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED} and quote.price is not None

    @staticmethod
    def _semantic_quote(quote: Quote, symbol: str) -> Quote | None:
        """Normalize valid provider data into explicit market semantics.

        A provider can return a valid last price while its timestamp is outside
        the freshness SLA. That is data semantics, not a provider outage. During
        a closed primary session it is surfaced as MARKET_CLOSED; otherwise it
        remains STALE. Neither state is allowed to trip the provider circuit.
        """
        if quote.price is None:
            return None
        if quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED, QuoteStatus.MARKET_CLOSED}:
            if quote.status == QuoteStatus.MARKET_CLOSED:
                return quote.model_copy(update={"market_open": False})
            return quote.model_copy(update={"market_open": True if quote.market_open is None else quote.market_open})
        if quote.status != QuoteStatus.STALE:
            return None

        open_now = is_market_open(symbol)
        if not open_now:
            return quote.model_copy(update={
                "status": QuoteStatus.MARKET_CLOSED,
                "market_open": False,
                "error": "Market is closed; provider returned the last validated quote.",
                "error_code": None,
            })
        return quote.model_copy(update={"status": QuoteStatus.STALE, "market_open": True})

    @staticmethod
    def _semantic_rank(quote: Quote) -> int:
        return {
            QuoteStatus.LIVE: 4,
            QuoteStatus.DELAYED: 3,
            QuoteStatus.MARKET_CLOSED: 2,
            QuoteStatus.STALE: 1,
        }.get(quote.status, 0)

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
        semantic_results: dict[str, Quote] = {}
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
            if provider.name == "twelve_data":
                budget = self._available_twelve_data_quote_budget(provider)
                if budget <= 0:
                    state = self._state(provider)
                    state.last_error = "Scanner quote budget exhausted; routing to fallback providers."
                    state.last_error_code = ProviderErrorCode.QUOTA_EXHAUSTED
                    candidates = []
                else:
                    candidates = candidates[:budget]
                    self._reserve_twelve_data_quote_budget(len(candidates))

            if not candidates:
                continue

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

                    semantic = self._semantic_quote(quote, key)
                    if semantic is not None:
                        semantic = semantic.model_copy(update={
                            "latency_ms": latency_ms,
                            "provider_attempts": tuple(diagnostics[key]),
                            "fallback_used": provider.name != self.providers[0].name or bool(excluded),
                            "cache_hit": False,
                        })
                        previous = semantic_results.get(key)
                        if previous is None or self._semantic_rank(semantic) > self._semantic_rank(previous):
                            semantic_results[key] = semantic
                        if self._fresh_quote(semantic):
                            successful += 1
                            results[key] = semantic
                            self.quote_cache.set(key, semantic, settings.quote_cache_seconds, settings.stale_quote_seconds)
                        continue

                    code = self._normalized_error_code(quote)
                    provider_failure_codes.append(code)

                if successful:
                    self._record_success(provider, latency_ms)
                elif provider_failure_codes:
                    # Semantic states never enter this list. Only actual provider
                    # failures (including UNKNOWN when no valid quote exists) do.
                    code = provider_failure_codes[0]
                    detail = next((by_symbol[key].error for key in candidates if key in by_symbol and by_symbol[key].error), "Provider returned no usable quotes")
                    self._record_failure(provider, detail, latency_ms, code)

                # Keep semantic-but-not-current quotes eligible for a better fallback.
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
            if key in semantic_results:
                semantic = semantic_results[key]
                output[key] = semantic.model_copy(update={
                    "provider_attempts": tuple(diagnostics[key]),
                    "fallback_used": semantic.fallback_used or len(diagnostics[key]) > 1,
                })
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
