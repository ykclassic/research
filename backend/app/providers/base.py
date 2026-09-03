from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models import Quote
from app.models.market import (
    CompletenessStatus,
    FreshnessStatus,
    OHLCVDataset,
    Timeframe,
)


@dataclass(frozen=True)
class ProviderUsage:
    credits_used: int | None = None
    credits_remaining: int | None = None
    observed_at: datetime | None = None


class MarketDataProvider(ABC):
    name: str

    @property
    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @property
    def supports_batch_quotes(self) -> bool:
        """Whether the provider implements a native multi-symbol quote request."""
        return False

    @property
    def usage(self) -> ProviderUsage | None:
        """Most recently observed provider usage, when the provider exposes it."""
        return None

    @abstractmethod
    async def get_quote(self, internal_symbol: str) -> Quote:
        raise NotImplementedError

    async def get_quotes(self, internal_symbols: list[str]) -> list[Quote]:
        """Batch boundary with safe individual-symbol fallback for non-batch providers."""
        if not internal_symbols:
            return []
        return list(await asyncio.gather(*(self.get_quote(symbol) for symbol in internal_symbols)))

    @abstractmethod
    async def get_candles(
        self,
        internal_symbol: str,
        timeframe: Timeframe,
        outputsize: int = 250,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> OHLCVDataset:
        raise NotImplementedError

    async def health(self) -> bool:
        return self.configured


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def freshness_for_age(age_seconds: float | None, fresh_seconds: float) -> FreshnessStatus:
    if age_seconds is None:
        return FreshnessStatus.UNKNOWN
    if age_seconds < 0:
        return FreshnessStatus.UNKNOWN
    if age_seconds <= fresh_seconds:
        return FreshnessStatus.FRESH
    if age_seconds <= fresh_seconds * 3:
        return FreshnessStatus.DELAYED
    return FreshnessStatus.STALE


def dataset_completeness(dataset: OHLCVDataset) -> CompletenessStatus:
    if not dataset.candles:
        return CompletenessStatus.INVALID
    if any(not candle.is_complete for candle in dataset.candles):
        return CompletenessStatus.PARTIAL
    return CompletenessStatus.COMPLETE
