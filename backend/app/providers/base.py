from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.models import Quote
from app.models.market import OHLCVDataset, Timeframe


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    async def get_quote(self, internal_symbol: str) -> Quote:
        raise NotImplementedError

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

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError
