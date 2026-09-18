from datetime import datetime, timezone

import pytest

from app.models.market import Candle, Timeframe
from app.services.signal_candle_scheduler import SignalCandleScheduler


def _dataset(symbol: str, timeframe: Timeframe):
    from app.models.market import OHLCVDataset, FreshnessStatus, CompletenessStatus

    now = datetime.now(timezone.utc)
    candle = Candle(
        timestamp=now.replace(second=0, microsecond=0),
        open=100,
        high=101,
        low=99,
        close=100.5,
        volume=10,
        symbol=symbol,
        timeframe=timeframe,
        source="test",
        is_complete=True,
    )
    return OHLCVDataset(
        symbol=symbol,
        timeframe=timeframe,
        source="test",
        requested_at=now,
        provider_timestamp=candle.timestamp,
        candles=(candle,) * 40,
        request_latency_ms=1,
        freshness_status=FreshnessStatus.FRESH,
        freshness_age_seconds=0,
        completeness_status=CompletenessStatus.COMPLETE,
    )


class FakeQuoteService:
    def __init__(self):
        self.calls = 0
        self.orchestrator = self

    async def get_candles(self, symbol, timeframe, outputsize):
        self.calls += 1
        return _dataset(symbol, timeframe)


class FakeCryptoProvider:
    def __init__(self):
        self.calls = []

    async def get_candles(self, symbol, timeframe, outputsize):
        self.calls.append((symbol, timeframe, outputsize))
        return _dataset(symbol, timeframe)


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
    provider = FakeCryptoProvider()
    service = FakeQuoteService()
    scheduler = SignalCandleScheduler(service, provider)

    results = await __import__("asyncio").gather(
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
        scheduler.get_dataset("BTC/USDT", Timeframe.HOUR_1, 250),
    )

    assert len(results) == 3
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_required_datasets_are_acquired_sequentially():
    provider = FakeCryptoProvider()
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
