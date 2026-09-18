from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.models.market import OHLCVDataset, Timeframe
from app.providers.kraken_public import KrakenPublicProvider
from app.services.candle_freshness import require_current_completed_candles
from app.services.quote_service import QuoteService
from app.services.settings_integration import MarketDataPolicy, validate_dataset_policy
from app.symbols import normalize_symbol


@dataclass(frozen=True)
class _CachedDataset:
    dataset: OHLCVDataset
    completed_close: datetime
    expires_at: float


class SignalCandleScheduler:
    """Coalesced, timeframe-aware candle acquisition for one selected signal."""

    def __init__(
        self,
        quote_service: QuoteService,
        crypto_provider: KrakenPublicProvider,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.quote_service = quote_service
        self.crypto_provider = crypto_provider
        self._clock = clock
        self._cache: dict[str, _CachedDataset] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._cache_lock = asyncio.Lock()

    @staticmethod
    def _key(symbol: str, timeframe: Timeframe, limit: int) -> str:
        return f"{normalize_symbol(symbol).internal}|{Timeframe(timeframe).value}|{limit}"

    @staticmethod
    def _cache_ttl(dataset: OHLCVDataset) -> float:
        return max(30.0, float(dataset.timeframe.seconds))

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._cache_lock:
            return self._locks.setdefault(key, asyncio.Lock())

    async def _cached(self, key: str) -> OHLCVDataset | None:
        async with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if self._clock() >= entry.expires_at:
                self._cache.pop(key, None)
                return None
            try:
                return require_current_completed_candles(entry.dataset)
            except ValueError:
                self._cache.pop(key, None)
                return None

    async def _store(self, key: str, dataset: OHLCVDataset) -> OHLCVDataset:
        current = require_current_completed_candles(dataset)
        latest = current.latest_completed_candle
        if latest is None:
            raise ValueError(f"{current.symbol} {current.timeframe.value} has no completed candle.")
        entry = _CachedDataset(
            dataset=current,
            completed_close=latest.timestamp,
            expires_at=self._clock() + self._cache_ttl(current),
        )
        async with self._cache_lock:
            self._cache[key] = entry
        return current

    async def _fetch(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        policy: MarketDataPolicy | None,
    ) -> OHLCVDataset:
        mapping = normalize_symbol(symbol)

        if mapping.asset_class == "crypto":
            try:
                dataset = await asyncio.wait_for(
                    self.crypto_provider.get_candles(mapping.internal, timeframe, limit),
                    timeout=12.0,
                )
            except Exception as primary_exc:
                try:
                    dataset = await asyncio.wait_for(
                        self.quote_service.orchestrator.get_candles(
                            mapping.internal, timeframe, limit
                        ),
                        timeout=12.0,
                    )
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"{mapping.internal} {timeframe.value}: primary crypto candle "
                        f"provider failed ({primary_exc}); fallback failed ({fallback_exc})"
                    ) from fallback_exc
        else:
            try:
                dataset = await asyncio.wait_for(
                    self.quote_service.orchestrator.get_candles(
                        mapping.internal, timeframe, limit
                    ),
                    timeout=12.0,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"{mapping.internal} {timeframe.value}: candle provider exceeded "
                    "the 12s signal acquisition budget"
                ) from exc

        if policy is not None:
            validate_dataset_policy(dataset, policy)
        return require_current_completed_candles(dataset)

    async def get_dataset(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        policy: MarketDataPolicy | None = None,
    ) -> OHLCVDataset:
        key = self._key(symbol, timeframe, limit)
        cached = await self._cached(key)
        if cached is not None:
            if policy is not None:
                validate_dataset_policy(cached, policy)
            return cached

        lock = await self._get_lock(key)
        async with lock:
            cached = await self._cached(key)
            if cached is not None:
                if policy is not None:
                    validate_dataset_policy(cached, policy)
                return cached
            dataset = await self._fetch(symbol, timeframe, limit, policy)
            return await self._store(key, dataset)

    async def get_required_datasets(
        self,
        symbol: str,
        timeframes: tuple[Timeframe, ...],
        limit: int,
        policy: MarketDataPolicy | None = None,
    ) -> dict[Timeframe, OHLCVDataset]:
        datasets: dict[Timeframe, OHLCVDataset] = {}
        for timeframe in timeframes:
            datasets[timeframe] = await self.get_dataset(symbol, timeframe, limit, policy)
        return datasets

    async def invalidate(
        self,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
    ) -> None:
        async with self._cache_lock:
            if symbol is None and timeframe is None:
                self._cache.clear()
                return
            normalized = normalize_symbol(symbol).internal if symbol else None
            for key in list(self._cache):
                parts = key.split("|")
                if len(parts) != 3:
                    continue
                if normalized is not None and parts[0] != normalized:
                    continue
                if timeframe is not None and parts[1] != Timeframe(timeframe).value:
                    continue
                self._cache.pop(key, None)

    async def clear(self) -> None:
        await self.invalidate()

    async def stats(self) -> dict[str, int]:
        async with self._cache_lock:
            return {"entries": len(self._cache), "tracked_keys": len(self._locks)}
