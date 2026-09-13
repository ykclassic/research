from datetime import datetime, timedelta, timezone

import pytest

from app.models import Quote, QuoteStatus
from app.models.market import Candle, CompletenessStatus, FreshnessStatus, OHLCVDataset, Timeframe
from app.providers.base import MarketDataProvider
from app.providers.orchestrator import MarketDataOrchestrator


class StubCandleProvider(MarketDataProvider):
    name = "stub"

    def __init__(self, dataset: OHLCVDataset):
        self.dataset = dataset

    @property
    def configured(self) -> bool:
        return True

    async def get_quote(self, internal_symbol: str) -> Quote:
        return Quote(symbol=internal_symbol, status=QuoteStatus.UNAVAILABLE)

    async def get_candles(self, internal_symbol, timeframe, outputsize=250, start_date=None, end_date=None):
        return self.dataset


def _dataset(*, completed: bool) -> OHLCVDataset:
    start = datetime(2026, 9, 11, tzinfo=timezone.utc)
    candles = tuple(
        Candle(
            timestamp=start + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1000.0,
            symbol="GBP/USD",
            timeframe=Timeframe.DAY_1,
            source="stub",
            is_complete=completed,
        )
        for index in range(3)
    )
    return OHLCVDataset(
        symbol="GBP/USD",
        timeframe=Timeframe.DAY_1,
        source="stub",
        requested_at=start,
        provider_timestamp=candles[-1].timestamp,
        candles=candles,
        freshness_status=FreshnessStatus.STALE,
        freshness_age_seconds=172800.0,
        completeness_status=CompletenessStatus.COMPLETE if completed else CompletenessStatus.PARTIAL,
    )


@pytest.mark.asyncio
async def test_orchestrator_accepts_stale_but_completed_historical_dataset():
    dataset = _dataset(completed=True)
    orchestrator = MarketDataOrchestrator(providers=[StubCandleProvider(dataset)])

    result = await orchestrator.get_candles("GBP/USD", Timeframe.DAY_1, 300)

    assert result.source == "stub"
    assert result.freshness_status == FreshnessStatus.STALE
    assert len(result.completed_candles) == 3
    assert result.cache_hit is False


@pytest.mark.asyncio
async def test_orchestrator_rejects_dataset_with_no_completed_candles():
    dataset = _dataset(completed=False)
    orchestrator = MarketDataOrchestrator(providers=[StubCandleProvider(dataset)])

    with pytest.raises(RuntimeError, match="All configured market-data providers were unavailable"):
        await orchestrator.get_candles("GBP/USD", Timeframe.DAY_1, 300)
