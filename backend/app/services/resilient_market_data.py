from __future__ import annotations

import asyncio
from typing import Any

from app.models.market import OHLCVDataset, Timeframe
from app.providers.orchestrator import MarketDataOrchestrator, market_data


class ResilientMarketDataOrchestrator:
    """Compatibility proxy with a single bounded candle recovery attempt."""

    def __init__(self, delegate: MarketDataOrchestrator | None = None) -> None:
        self._delegate = delegate or market_data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int,
        *,
        start_date=None,
        end_date=None,
    ) -> OHLCVDataset:
        try:
            return await self._delegate.get_candles(
                symbol,
                timeframe,
                limit,
                start_date=start_date,
                end_date=end_date,
            )
        except (RuntimeError, asyncio.TimeoutError) as first_error:
            # Historical-range requests must remain deterministic and must not
            # be retried through a newly initialized provider scheduler.
            if start_date is not None or end_date is not None:
                raise
            recovery = MarketDataOrchestrator()
            try:
                return await recovery.get_candles(symbol, timeframe, limit)
            except Exception as recovery_error:
                raise first_error from recovery_error


market_data_resilient = ResilientMarketDataOrchestrator(market_data)
