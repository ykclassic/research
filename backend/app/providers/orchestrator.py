from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Literal

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
from app.services.quota_scheduler import QuoteQuotaScheduler
from app.symbols import normalize_symbol

HealthDomain = Literal["quote", "candles"]


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
    """Canonical provider boundary with independent quote/candle health."""

    _ROUTING_ORDER = {"twelve_data": 0, "finnhub": 1, "alpha_vantage": 2}

    @classmethod
    def _route_providers(cls, providers: list[MarketDataProvider]) -> list[MarketDataProvider]:
        return sorted(providers, key=lambda provider: cls._ROUTING_ORDER.get(provider.name, 99))

    def __init__(self, providers: list[MarketDataProvider] | None = None) -> None:
        configured = providers or [TwelveDataProvider(), FinnhubProvider(), AlphaVantageProvider()]
        self.providers = self._route_providers(configured)
        self._health: dict[tuple[str, HealthDomain], ProviderHealthState] = {
            (provider.name, domain): ProviderHealthState()
            for provider in self.providers
            for domain in ("quote", "candles")
        }
        self._lock = Lock()
        self._twelve_data_quota = QuoteQuotaScheduler(
            minute_budget=settings.twelve_data_quote_minute_budget,
            daily_budget=settings.twelve_data_quote_daily_budget,
            protected_capacity=settings.twelve_data_candle_minute_reserve,
        )
        self.quote_cache: CanonicalMarketCache[Quote] = CanonicalMarketCache()
        self.candle_cache: CanonicalMarketCache[OHLCVDataset] = CanonicalMarketCache()

    def _state(self, provider: MarketDataProvider, domain: HealthDomain = "quote") -> ProviderHealthState:
        return self._health[(provider.name, domain)]

    def _sync_usage(self, provider: MarketDataProvider) -> None:
        usage = provider.usage
        if usage is None:
            return
        state = self._state(provider, "quote")
        state.credits_used = usage.credits_used
        state.credits_remaining = usage.credits_remaining
        state.usage_observed_at = usage.observed_at
        if provider.name == "twelve_data":
            self._twelve_data_quota.reconcile(provider_remaining=usage.credits_remaining, observed_at=usage.observed_at)

    def _record_success(self, provider: MarketDataProvider, latency_ms: int, domain: HealthDomain = "quote") -> None:
        with self._lock:
            state = self._state(provider, domain)
            state.consecutive_failures = 0
            state.opened_until = 0.0
            state.last_latency_ms = latency_ms
            state.last_error = None
            state.last_error_code = None
            if domain == "quote":
                self._sync_usage(provider)

    def _record_failure(self, provider: MarketDataProvider, error: str, latency_ms: int, error_code: ProviderErrorCode, domain: HealthDomain = "quote") -> None:
        with self._lock:
            state = self._state(provider, domain)
            state.last_latency_ms = latency_ms
            state.last_error = error
            state.last_error_code = error_code
            if domain == "quote":
                self._sync_usage(provider)
            if error_code != ProviderErrorCode.SYMBOL_UNSUPPORTED:
                state.consecutive_failures += 1
                if state.consecutive_failures >= settings.provider_failure_threshold:
                    state.opened_until = time.monotonic() + settings.provider_circuit_cooldown_seconds

    def _available_twelve_data_quote_budget(self, provider: MarketDataProvider) -> int:
        self._sync_usage(provider)
        snapshot = self._twelve_data_quota.snapshot()
        state = self._state(provider, "quote")
        state.quote_budget_remaining = snapshot.available
        state.daily_quote_budget_remaining = snapshot.daily_remaining
        return snapshot.available

    def _reserve_twelve_data_quote_budget(self, requested: int) -> int:
        granted = self._twelve_data_quota.reserve(requested)
        state = self._health.get(("twelve_data", "quote"))
        if state is not None:
            snapshot = self._twelve_data_quota.snapshot()
            state.quote_budget_remaining = snapshot.available
            state.daily_quote_budget_remaining = snapshot.daily_remaining
        return granted

    def _reserve_twelve_data_candle_budget(self) -> bool:
        granted = self._twelve_data_quota.reserve_candle(1)
        state = self._health.get(("twelve_data", "candles"))
        if state is not None:
            snapshot = self._twelve_data_quota.snapshot()
            state.quote_budget_remaining = snapshot.candle_remaining
            state.daily_quote_budget_remaining = snapshot.daily_remaining
        return granted == 1

    def _release_twelve_data_candle_budget(self) -> None:
        self._twelve_data_quota.release_candle(1)
        state = self._health.get(("twelve_data", "candles"))
        if state is not None:
            snapshot = self._twelve_data_quota.snapshot()
            state.quote_budget_remaining = snapshot.candle_remaining
            state.daily_quote_budget_remaining = snapshot.daily_remaining

    def provider_status(self, domain: HealthDomain = "quote") -> list[ProviderStatus]:
        statuses: list[ProviderStatus] = []
        for provider in self.providers:
            state = self._state(provider, domain)
            quote_budget = state.quote_budget_remaining if domain == "quote" else None
            daily_budget = state.daily_quote_budget_remaining if domain == "quote" else None
            if provider.name == "twelve_data" and domain == "quote":
                quote_budget = self._available_twelve_data_quote_budget(provider)
                daily_budget = state.daily_quote_budget_remaining
            statuses.append(ProviderStatus(
                provider=provider.name, configured=provider.configured, reachable=None,
                circuit_open=state.circuit_open, consecutive_failures=state.consecutive_failures,
                last_latency_ms=state.last_latency_ms, last_error=state.last_error,
                last_error_code=state.last_error_code,
                credits_used=state.credits_used if domain == "quote" else None,
                credits_remaining=state.credits_remaining if domain == "quote" else None,
                usage_observed_at=state.usage_observed_at if domain == "quote" else None,
                quote_budget_remaining=quote_budget, daily_quote_budget_remaining=daily_budget,
                message=(f"Configured; {domain} health is learned from real requests." if provider.configured else "Provider key is not configured."),
            ))
        return statuses

    @property
    def providers_by_name(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self.providers)

    @staticmethod
    def _fresh_quote(quote: Quote) -> bool:
        return quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED} and quote.price is not None

    @staticmethod
    def _semantic_quote(quote: Quote, symbol: str) -> Quote | None:
        if quote.price is None:
            return None
        if quote.status in {QuoteStatus.LIVE, QuoteStatus.DELAYED, QuoteStatus.MARKET_CLOSED}:
            if quote.status == QuoteStatus.MARKET_CLOSED:
                return quote.model_copy(update={"market_open": False})
            return quote.model_copy(update={"market_open": True if quote.market_open is None else quote.market_open})
        if quote.status != QuoteStatus.STALE:
            return None
        if not is_market_open(symbol):
            return quote.model_copy(update={"status": QuoteStatus.MARKET_CLOSED, "market_open": False, "error": "Market is closed; provider returned the last validated quote.", "error_code": None})
        return quote.model_copy(update={"status": QuoteStatus.STALE, "market_open": True})

    @staticmethod
    def _semantic_rank(quote: Quote) -> int:
        return {QuoteStatus.LIVE: 4, QuoteStatus.DELAYED: 3, QuoteStatus.MARKET_CLOSED: 2, QuoteStatus.STALE: 1}.get(quote.status, 0)

    @staticmethod
    def _fresh_dataset(dataset: OHLCVDataset) -> bool:
        return dataset.freshness_status in {FreshnessStatus.FRESH, FreshnessStatus.DELAYED} and bool(dataset.completed_candles)

    @staticmethod
    def _normalized_error_code(quote: Quote) -> ProviderErrorCode:
        return quote.error_code if quote.error_code is not None else classify_provider_error(message=quote.error)

    @staticmethod
    def _error_text(code: ProviderErrorCode, detail: str | None = None) -> str:
        label = error_label(code)
        return f"{label}: {detail}" if detail else label

    async def get_quote(self, symbol: str, *, force_refresh: bool = False, excluded_providers: set[str] | None = None) -> Quote:
        return (await self.get_quotes([symbol], force_refresh=force_refresh, excluded_providers=excluded_providers))[0]

    async def get_quotes(self, symbols: list[str], *, force_refresh: bool = False, excluded_providers: set[str] | None = None) -> list[Quote]:
        if not symbols:
            return []
        excluded = excluded_providers or set()
        mappings = [normalize_symbol(symbol) for symbol in symbols]
        keys = list(dict.fromkeys(mapping.internal for mapping in mappings))
        results: dict[str, Quote] = {}
        semantic_results: dict[str, Quote] = {}
        diagnostics = {key: [] for key in keys}
        remaining: list[str] = []
        for key in keys:
            cached = self.quote_cache.get(key, allow_stale=False)
            if cached is not None and not force_refresh and not excluded:
                quote, _ = cached
                results[key] = quote.model_copy(update={"cache_hit": True, "latency_ms": 0})
            else:
                remaining.append(key)
        for provider in self.providers:
            if not remaining:
                break
            if provider.name in excluded or not provider.configured or self._state(provider, "quote").circuit_open:
                continue
            candidates = list(remaining)
            if provider.name == "twelve_data":
                reservation = self._reserve_twelve_data_quote_budget(len(candidates))
                if reservation == 0:
                    state = self._state(provider, "quote")
                    state.last_error = "Quote quota scheduler has no capacity; routing to fallback providers."
                    state.last_error_code = ProviderErrorCode.QUOTA_EXHAUSTED
                    continue
                candidates = candidates[:reservation]
            started = time.perf_counter()
            try:
                quotes = await asyncio.wait_for(provider.get_quotes(candidates), timeout=settings.provider_timeout_seconds)
                latency_ms = int((time.perf_counter() - started) * 1000)
                by_symbol = {quote.symbol: quote for quote in quotes}
                semantic_success = False
                failures: list[ProviderErrorCode] = []
                for key in candidates:
                    diagnostics[key].append(provider.name)
                    quote = by_symbol.get(key)
                    if quote is None:
                        failures.append(ProviderErrorCode.PROVIDER_UNAVAILABLE)
                        continue
                    semantic = self._semantic_quote(quote, key)
                    if semantic is None:
                        failures.append(self._normalized_error_code(quote))
                        continue
                    semantic_success = True
                    semantic = semantic.model_copy(update={"latency_ms": latency_ms, "provider_attempts": tuple(diagnostics[key]), "fallback_used": provider.name != self.providers[0].name or bool(excluded), "cache_hit": False})
                    previous = semantic_results.get(key)
                    if previous is None or self._semantic_rank(semantic) > self._semantic_rank(previous):
                        semantic_results[key] = semantic
                    if self._fresh_quote(semantic):
                        results[key] = semantic
                        self.quote_cache.set(key, semantic, settings.quote_cache_seconds, settings.stale_quote_seconds)
                if semantic_success:
                    self._record_success(provider, latency_ms, "quote")
                elif failures:
                    detail = next((by_symbol[key].error for key in candidates if key in by_symbol and by_symbol[key].error), "Provider returned no usable quotes")
                    self._record_failure(provider, detail, latency_ms, failures[0], "quote")
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                code = classify_provider_error(exc)
                for key in candidates:
                    diagnostics[key].append(provider.name)
                self._record_failure(provider, str(exc), latency_ms, code, "quote")
            finally:
                if provider.name == "twelve_data":
                    self._available_twelve_data_quote_budget(provider)
            remaining = [key for key in remaining if key not in results]
        output: dict[str, Quote] = {}
        for key in keys:
            if key in results:
                output[key] = results[key]
                continue
            if key in semantic_results:
                semantic = semantic_results[key]
                output[key] = semantic.model_copy(update={"provider_attempts": tuple(diagnostics[key]), "fallback_used": semantic.fallback_used or len(diagnostics[key]) > 1})
                continue
            cached = self.quote_cache.get(key, allow_stale=True)
            mapping = normalize_symbol(key)
            if cached is not None:
                quote, age = cached
                if quote.status == QuoteStatus.STALE or age > settings.quote_cache_seconds:
                    output[key] = quote.model_copy(update={"status": QuoteStatus.STALE, "freshness_status": FreshnessStatus.STALE, "freshness_age_seconds": max(quote.freshness_age_seconds or 0.0, age), "error": "All live providers were unavailable; serving the last validated market quote.", "error_code": ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE, "cache_hit": True, "fallback_used": True, "provider_attempts": tuple(diagnostics[key]) or quote.provider_attempts, "latency_ms": 0})
                else:
                    output[key] = quote.model_copy(update={"cache_hit": True, "fallback_used": True, "provider_attempts": tuple(diagnostics[key]) or quote.provider_attempts, "latency_ms": 0})
                continue
            errors = []
            for provider in self.providers:
                state = self._state(provider, "quote")
                if provider.name in diagnostics[key] and state.last_error:
                    errors.append(f"{provider.name}={error_label(state.last_error_code)}")
            detail = "; ".join(errors) or "No configured provider produced a usable quote."
            output[key] = Quote(symbol=key, provider_symbol=mapping.twelve_data, status=QuoteStatus.UNAVAILABLE, source=None, error=f"{self._error_text(ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE)}: {detail}", error_code=ProviderErrorCode.ALL_PROVIDERS_UNAVAILABLE, fallback_used=bool(diagnostics[key]), provider_attempts=tuple(diagnostics[key]))
        return [output[normalize_symbol(symbol).internal] for symbol in symbols]

    async def get_candles(self, symbol: str, timeframe: Timeframe, outputsize: int = 250, start_date: datetime | None = None, end_date: datetime | None = None, *, excluded_providers: set[str] | None = None) -> OHLCVDataset:
        mapping = normalize_symbol(symbol)
        timeframe = Timeframe(timeframe)
        range_key = "recent" if start_date is None else f"{start_date.isoformat()}:{end_date.isoformat()}"
        request_key = f"{mapping.internal}|{timeframe.value}|{outputsize}|{range_key}"
        canonical_key = f"canonical|{mapping.internal}|{timeframe.value}|{range_key}"
        canonical_prefix = f"canonical|{mapping.internal}|{timeframe.value}|"
        excluded = excluded_providers or set()
        attempts: list[str] = []

        if not excluded:
            cached = self.candle_cache.get(request_key, allow_stale=False)
            if cached is None:
                cached = self.candle_cache.get(canonical_key, allow_stale=False)
            if cached is None:
                cached = self.candle_cache.get_latest(canonical_prefix, allow_stale=False)
            if cached is not None:
                dataset, age = cached
                return dataset.model_copy(update={"cache_hit": True, "cache_age_seconds": age, "request_latency_ms": 0})

        for provider in self.providers:
            candle_state = self._state(provider, "candles")
            if provider.name in excluded or not provider.configured or candle_state.circuit_open:
                continue
            candle_reserved = False
            if provider.name == "twelve_data" and not self._reserve_twelve_data_candle_budget():
                snapshot = self._twelve_data_quota.snapshot()
                # A fresh zero balance is a minute-window condition, not a
                # provider failure. If the daily allowance remains, wait only
                # for the imminent Twelve Data minute reset and retry once.
                if snapshot.provider_remaining == 0 and snapshot.daily_remaining > 0:
                    wait_seconds = self._twelve_data_quota.seconds_until_minute_reset()
                    if 0 < wait_seconds <= 6:
                        await asyncio.sleep(wait_seconds + 0.05)
                        if self._reserve_twelve_data_candle_budget():
                            candle_reserved = True
                        else:
                            candle_state.last_error = "Candle quota remains unavailable after the Twelve Data minute reset; routing to fallback providers."
                            candle_state.last_error_code = ProviderErrorCode.QUOTA_EXHAUSTED
                            continue
                    else:
                        candle_state.last_error = "Candle quota scheduler has no capacity; routing to fallback providers."
                        candle_state.last_error_code = ProviderErrorCode.QUOTA_EXHAUSTED
                        continue
                else:
                    candle_state.last_error = "Candle quota scheduler has no capacity; routing to fallback providers."
                    candle_state.last_error_code = ProviderErrorCode.QUOTA_EXHAUSTED
                    continue
            elif provider.name == "twelve_data":
                candle_reserved = True
            attempts.append(provider.name)
            started = time.perf_counter()
            try:
                dataset = await asyncio.wait_for(
                    provider.get_candles(mapping.internal, timeframe, outputsize, start_date=start_date, end_date=end_date),
                    timeout=max(settings.analysis_timeout_seconds, settings.provider_timeout_seconds),
                )
                latency_ms = int((time.perf_counter() - started) * 1000)
                if not self._fresh_dataset(dataset):
                    self._record_failure(provider, "Provider candle set is stale or incomplete", latency_ms, ProviderErrorCode.PROVIDER_UNAVAILABLE, "candles")
                    continue
                self._record_success(provider, latency_ms, "candles")
                dataset = dataset.model_copy(update={
                    "request_latency_ms": latency_ms,
                    "provider_attempts": tuple(attempts),
                    "fallback_used": provider.name != self.providers[0].name or bool(excluded),
                    "cache_hit": False,
                    "cache_age_seconds": 0.0,
                })
                self.candle_cache.set(request_key, dataset, settings.quote_cache_seconds, settings.market_cache_stale_seconds)
                self.candle_cache.set(canonical_key, dataset, settings.quote_cache_seconds, settings.market_cache_stale_seconds)
                return dataset
            except Exception as exc:
                self._record_failure(provider, str(exc), int((time.perf_counter() - started) * 1000), classify_provider_error(exc), "candles")
            finally:
                if candle_reserved:
                    self._release_twelve_data_candle_budget()

        cached = self.candle_cache.get(request_key, allow_stale=True)
        if cached is None:
            cached = self.candle_cache.get(canonical_key, allow_stale=True)
        if cached is None:
            cached = self.candle_cache.get_latest(canonical_prefix, allow_stale=True)
        if cached is not None:
            dataset, age = cached
            stale = dataset.freshness_status == FreshnessStatus.STALE or age > settings.quote_cache_seconds
            if stale:
                dataset = dataset.model_copy(update={
                    "freshness_status": FreshnessStatus.STALE,
                    "freshness_age_seconds": max(dataset.freshness_age_seconds or 0.0, age),
                })
            return dataset.model_copy(update={
                "fallback_used": True,
                "cache_hit": True,
                "cache_age_seconds": age,
                "provider_attempts": tuple(attempts) or dataset.provider_attempts,
                "request_latency_ms": 0,
            })
        raise RuntimeError("All configured market-data providers were unavailable and no canonical candle cache entry exists.")


market_data = MarketDataOrchestrator()
