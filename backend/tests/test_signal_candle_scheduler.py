from datetime import datetime, timedelta, timezone

import asyncio
import pytest

from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.services.signal_candle_scheduler import SignalCandleScheduler


def _dataset(symbol: str, timeframe: Timeframe) -> OHLCVDataset:
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=timeframe.seconds * 40)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(seconds=timeframe.seconds * index),
            open=100 + index * 0.01,
            high=101 + index * 0.01,
            low=99 + index * 0.01,
            close=100.5 + index * 0.01,
            volume=10,
            symbol=symbol,
            timeframe=timeframe,
            source="test",
            is_complete=True,
        )
        for index in range(40)
    )
    return OHLCVDataset(
        symbol=symbol,
        timeframe=timeframe,
        source="test",
        requested_at=now,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
        request_latency_ms=1,
        freshness_status=FreshnessStatus.FRESH,
        freshness_age_seconds=0,
        completeness_status=CompletenessStatus.COMPLETE,
    )


class FakeQuoteService:
    def __init__(self) -> None:
        self.calls = 0
        self.orchestrator = self

    async def get_candles(self, symbol, timeframe, outputsize):
        self.calls += 1
        return _dataset(symbol, timeframe)


class FakeCryptoProvider:
    def __init__(self, delay: float = 0) -> None:
        self.calls = []
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def get_candles(self, symbol, timeframe, outputsize):
        self.calls.append((symbol, timeframe, outputsize))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return _dataset(symbol, timeframe)
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_scheduler_caches_each_completed_timeframe():
    provider = FakeCryptoProvider()
    service = FakeQuoteService()
    scheduler = SignalCandleScheduler(service, provider)

    first = await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)
    second = await scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250)

    assert first is not None
    assert second is not None
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_scheduler_coalesces_concurrent_same_key_requests():
    provider = FakeCryptoProvider(delay=0.02)
    service = FakeQuoteService()
    scheduler = SignalCandleScheduler(service, provider)

    results = await asyncio.gather(
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
    )

    assert len(results) == 3
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_required_datasets_are_acquired_sequentially():
    provider = FakeCryptoProvider(delay=0.01)
    service = FakeQuoteService()
    scheduler = SignalCandleScheduler(service, provider)

    datasets = await scheduler.get_required_datasets(
        "BTC/USDT",
        (Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15),
        250,
    )

    assert tuple(datasets) == (
        Timeframe.HOUR_4,
        Timeframe.HOUR_1,
        Timeframe.MINUTE_15,
    )
    assert len(provider.calls) == 3
    assert provider.max_active == 1


@pytest.mark.asyncio
async def test_selected_pair_does_not_acquire_another_symbol():
    provider = FakeCryptoProvider()
    service = FakeQuoteService()
    scheduler = SignalCandleScheduler(service, provider)

    await scheduler.get_required_datasets(
        "BNB/USDT",
        (Timeframe.DAY_1, Timeframe.HOUR_4, Timeframe.HOUR_1, Timeframe.MINUTE_15),
        250,
    )

    assert {call[0] for call in provider.calls} == {"BNB/USDT"}
    assert len(provider.calls) == 4
